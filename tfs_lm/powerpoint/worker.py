"""The worker-thread half of a PowerPoint send.

Ported from Images_To_PPT_v3's image_file_worker, with its four real
bugs fixed: it never called CoInitialize (COM on a worker thread needs
it), it returned on the first per-image error instead of isolating,
it inserted every slide at the SAME position (silently reversing the
batch), and it placed pictures at a 1x1 point placeholder size.

What lands on a slide, per the user's design:
  * the ORIGINAL (unlabelled) image, fitted to the slide;
  * optionally a NATIVE, editable label object — a rounded-rectangle
    plate behind key/value TEXT BOXES, all grouped — built from the
    LabelSpec rather than rasterised, so it can be moved, resized,
    restyled and text-edited in PowerPoint. Text boxes, not a table:
    PowerPoint refuses to group a table with a shape, and the group is
    what makes the label move as one object;
  * always Notes carrying the filename plus the selected metadata, so
    the values survive even if the label styling is not wanted.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtGui import QColor

from .. import defaults
from ..label.layout import LaidCustom, build_layout
from ..label.spec import LabelSpec

logger = logging.getLogger(__name__)

try:  # pragma: no cover - import availability is environment-dependent
    import pythoncom  # noqa: F401
    from win32com import client as win32_client  # noqa: F401

    PYWIN32_AVAILABLE = True
except Exception:  # noqa: BLE001 - ImportError, or a broken install
    PYWIN32_AVAILABLE = False

# Office enum values, spelled out rather than imported so the module
# loads without pywin32.
MSO_FALSE = 0
MSO_TRUE = -1
MSO_SHAPE_ROUNDED_RECTANGLE = 5
MSO_TEXT_ORIENTATION_HORIZONTAL = 1
PP_LAYOUT_BLANK = 12
PP_ALIGN_LEFT = 1
PP_ALIGN_CENTER = 2
PP_ALIGN_RIGHT = 3
PP_AUTOSIZE_NONE = 0
PP_ALERTS_NONE = 2  # PpAlertLevel.ppAlertsNone
# PpPlaceholderType values that mean "a content area a picture may
# fill": Content (Object), Bitmap and Picture placeholders. Titles,
# bodies, footers and dates keep their jobs.
PP_PLACEHOLDER_OBJECT = 7
PP_PLACEHOLDER_BITMAP = 9
PP_PLACEHOLDER_PICTURE = 18
CONTENT_PLACEHOLDER_TYPES = frozenset({
    PP_PLACEHOLDER_OBJECT, PP_PLACEHOLDER_BITMAP, PP_PLACEHOLDER_PICTURE,
})
# MsoShapeType: the shape AddPicture2 returns when an empty content
# placeholder ABSORBED the insert (the shape IS the placeholder).
MSO_SHAPE_TYPE_PLACEHOLDER = 14
# Where images start, after a title slide — the reference's convention.
FIRST_CONTENT_POSITION = 2

# The label style's alignment enum -> PowerPoint's.
_PP_ALIGNMENT = {
    defaults.ALIGN_LEFT: PP_ALIGN_LEFT,
    defaults.ALIGN_CENTER: PP_ALIGN_CENTER,
    defaults.ALIGN_RIGHT: PP_ALIGN_RIGHT,
}


class _SendStopped(Exception):
    """Stop landed inside a slide's label build.

    Distinct from a per-image failure: the item is neither sent nor
    failed, the partially built slide is removed (the deck holds whole
    slides only), and the run unwinds to the normal stopped ending.
    """


@dataclass(frozen=True, slots=True)
class PptItem:
    """One image's slide. `label_spec` is None for an image-only send."""

    source: Path
    notes: str = ""
    label_spec: LabelSpec | None = None


@dataclass(frozen=True, slots=True)
class PptSettings:
    """Frozen snapshot of the card's settings, safe for the worker."""

    transition_enabled: bool = defaults.TRANSITION_ENABLED_DEFAULT
    transition_index: int = defaults.TRANSITION_SLIDE_INDEX_DEFAULT
    image_index: int = defaults.IMAGE_SLIDE_INDEX_DEFAULT


@dataclass
class PptSendResults:
    """Filled in place by the worker; read after the job finishes."""

    sent: list[Path] = field(default_factory=list)
    failures: list[tuple[Path, str]] = field(default_factory=list)
    template_mode: bool | None = None
    transition_fallback: bool = False
    error_reason: str | None = None

    def clear(self) -> None:
        self.sent.clear()
        self.failures.clear()
        self.template_mode = None
        self.transition_fallback = False
        self.error_reason = None


def _rgb(color: str) -> int:
    """Qt colour string -> PowerPoint's BGR-packed integer."""

    qc = QColor(color)
    if not qc.isValid():
        qc = QColor("#000000")
    return qc.blue() << 16 | qc.green() << 8 | qc.red()


def resolve_image_layout(presentation, image_index: int):
    """(layout, template_mode) for the image slides.

    Probed ONCE per presentation: a batch that silently mixed template
    and generic slides would be more confusing than one that is
    consistently generic. Any failure — no Designs, no SlideMaster, an
    index past the end — means the deck is not the user's template, so
    the send falls back to plain blank slides.
    """

    try:
        layout = presentation.Designs(1).SlideMaster.CustomLayouts(image_index)
    except Exception:  # noqa: BLE001 - com_error, AttributeError, IndexError...
        logger.warning(
            "Image slide layout %d unavailable; using generic slides",
            image_index,
            exc_info=True,
        )
        return None, False
    return layout, True


class PptSendWorker(QObject):
    """Inserts one slide per item into the active presentation."""

    progressUpdated = Signal(int, int)
    statusUpdated = Signal(str)
    finished = Signal(bool)

    def __init__(
        self,
        items: list[PptItem],
        settings: PptSettings,
        results: PptSendResults,
        stop_event: threading.Event,
    ) -> None:
        super().__init__()
        self._items = items
        self._settings = settings
        self._results = results
        self._stop = stop_event
        # Per-send memo: whether the image layout's notes page has the
        # body placeholder. The layout is uniform for the whole batch
        # (probed once), so one failure means every slide would fail —
        # skip the 7-dot chain instead of raising per slide.
        self._notes_supported: bool | None = None
        # Per-send memo, like _notes_supported: whether Shape.Duplicate
        # cloning works against this PowerPoint. One failure predicts
        # the rest (same binding, same deck), so the send drops to
        # scratch-building every box — styling fidelity is never lost,
        # only the speed-up.
        self._clone_supported: bool | None = None

    # --- Lifecycle -------------------------------------------------------

    @Slot()
    def run(self) -> None:
        completed = False
        original_alerts = None  # read by the finally on every path
        if not PYWIN32_AVAILABLE:  # pragma: no cover - guarded upstream too
            self._results.error_reason = defaults.STATUS_PPT_UNAVAILABLE
            self.finished.emit(False)
            return

        import pythoncom

        # The reference omits this. COM on a non-main thread needs its
        # own apartment or Dispatch fails (or worse, works by luck).
        pythoncom.CoInitialize()
        try:
            self.statusUpdated.emit(defaults.STATUS_PPT_CONNECTING)
            self.progressUpdated.emit(-1, -1)
            ppt = self._create_application()
            presentation = self._active_presentation(ppt)
            if presentation is None:
                self._results.error_reason = defaults.STATUS_PPT_NO_PRESENTATION
                return

            # A PowerPoint alert dialog would block the worker thread
            # invisibly — nobody is watching for a modal mid-send.
            # Suppressed for the send only; the finally restores it.
            try:
                original_alerts = ppt.DisplayAlerts
                ppt.DisplayAlerts = PP_ALERTS_NONE
            except Exception:  # noqa: BLE001 - insurance, never load-bearing
                logger.debug("Could not suppress PowerPoint alerts",
                             exc_info=True)

            image_layout, template_mode = resolve_image_layout(
                presentation, self._settings.image_index
            )
            self._results.template_mode = template_mode

            position = min(
                FIRST_CONTENT_POSITION, self._slide_count(presentation) + 1
            )
            if self._settings.transition_enabled:
                position = self._add_transition(presentation, position)

            # Two progress units per slide — picture, then label — so
            # the bar moves INSIDE big labelled slides instead of
            # freezing for the whole block.
            total = len(self._items)
            for index, item in enumerate(self._items):
                if self._stop.is_set():
                    return
                self.statusUpdated.emit(f"Sending {item.source.name}")
                try:
                    self._add_image_slide(
                        presentation, position, item, image_layout,
                        template_mode, progress=(index, total),
                    )
                except _SendStopped:
                    # Before the generic handler: not sent, not a
                    # failure — the finally reports the stop.
                    return
                except Exception as exc:  # noqa: BLE001 - per-image isolation
                    logger.exception("PPT slide failed for %r", str(item.source))
                    self._results.failures.append((item.source, str(exc)))
                    if not self._presentation_alive(presentation):
                        self._results.error_reason = defaults.STATUS_PPT_CLOSED
                        return
                else:
                    self._results.sent.append(item.source)
                    position += 1
                self.progressUpdated.emit(2 * index + 2, 2 * total)
            completed = True
        except Exception as exc:  # noqa: BLE001 - reported, never fatal
            logger.exception("PowerPoint send failed")
            self._results.error_reason = str(exc)
        finally:
            # Restore BEFORE the refs drop and the apartment closes;
            # self-guarded so a closed PowerPoint cannot mask the real
            # error (or the successful completion).
            try:
                if original_alerts is not None:
                    ppt.DisplayAlerts = original_alerts
            except Exception:  # noqa: BLE001 - best effort
                logger.debug("Could not restore PowerPoint alerts",
                             exc_info=True)
            presentation = None
            ppt = None
            pythoncom.CoUninitialize()
            self.finished.emit(completed and not self._stop.is_set())

    # --- Presentation helpers --------------------------------------------

    @staticmethod
    def _create_application():
        """The PowerPoint Application object, early-bound when possible.

        gencache.EnsureDispatch generates and caches makepy classes for
        the PowerPoint type library: property accesses then carry
        compiled DISPIDs instead of dynamic dispatch's per-object
        type-info round trips — the wrap overhead was ~60% of a
        labelled send's cross-process traffic. The very first call
        generates the cache (multi-second, deliberately IN-SEND behind
        the already-shown "Connecting…" status and indeterminate bar —
        a startup warm-up would launch PowerPoint itself); every later
        send hits the on-disk cache. Falls back to late binding on
        read-only installs, frozen builds, or a corrupted cache.
        """

        try:
            return win32_client.gencache.EnsureDispatch(
                "PowerPoint.Application"
            )
        except Exception:  # noqa: BLE001 - never block the send on binding
            logger.warning(
                "Early binding unavailable; using dynamic dispatch. "
                "(A corrupted makepy cache is reset by deleting the "
                "win32com gen_py directory.)",
                exc_info=True,
            )
            return win32_client.Dispatch("PowerPoint.Application")

    @staticmethod
    def _active_presentation(ppt):
        try:
            presentation = ppt.ActivePresentation
            presentation.Slides.Count  # noqa: B018 - probe that it is real
        except Exception:  # noqa: BLE001
            logger.warning("No active PowerPoint presentation", exc_info=True)
            return None
        return presentation

    @staticmethod
    def _slide_count(presentation) -> int:
        try:
            return int(presentation.Slides.Count)
        except Exception:  # noqa: BLE001
            return 0

    @staticmethod
    def _presentation_alive(presentation) -> bool:
        try:
            presentation.Slides.Count  # noqa: B018
        except Exception:  # noqa: BLE001
            return False
        return True

    def _add_transition(self, presentation, position: int) -> int:
        """Insert the divider slide; returns the next insert position."""

        slides = presentation.Slides
        target = min(position, self._collection_count(slides) + 1)
        try:
            layout = presentation.Designs(1).SlideMaster.CustomLayouts(
                self._settings.transition_index
            )
            slides.AddSlide(target, layout)
        except Exception:  # noqa: BLE001 - independent of the image fallback
            logger.warning(
                "Transition layout %d unavailable; generic divider",
                self._settings.transition_index,
                exc_info=True,
            )
            self._results.transition_fallback = True
            try:
                slides.Add(target, PP_LAYOUT_BLANK)
            except Exception:  # noqa: BLE001 - a divider is optional
                logger.exception("Could not add a transition slide")
                return position
        return position + 1

    @staticmethod
    def _collection_count(slides) -> int:
        try:
            return int(slides.Count)
        except Exception:  # noqa: BLE001
            return 0

    # --- Slide building ---------------------------------------------------

    def _add_image_slide(
        self, presentation, position: int, item: PptItem, image_layout,
        template_mode, progress: tuple[int, int] | None = None,
    ) -> None:
        # One Slides fetch per slide; the Count clamp stays because the
        # user can delete slides from the live deck mid-send.
        slides = presentation.Slides
        target = min(position, self._collection_count(slides) + 1)
        if template_mode:
            slide = slides.AddSlide(target, image_layout)
        else:
            slide = slides.Add(target, PP_LAYOUT_BLANK)

        try:
            picture = self._place_picture(presentation, slide, item.source)
        except Exception:
            # A pictureless slide must not linger in the deck: delete it
            # before letting the per-image handler record the failure
            # (otherwise the orphan sits where the next slide inserts).
            try:
                slide.Delete()
            except Exception:  # noqa: BLE001 - best effort
                logger.exception("Could not remove the failed slide")
            raise

        if item.label_spec is not None and item.label_spec.cells:
            if progress is not None:
                index, total = progress
                self.progressUpdated.emit(2 * index + 1, 2 * total)
                self.statusUpdated.emit(f"Labelling {item.source.name}")
            try:
                self._place_label(slide, picture, item.label_spec)
            except _SendStopped:
                # Stop landed mid-label: the deck holds whole slides
                # only, so the partial one goes — picture and all —
                # before the stop unwinds to run().
                try:
                    slide.Delete()
                except Exception:  # noqa: BLE001 - best effort
                    logger.exception("Could not remove the stopped slide")
                raise
            except Exception:  # noqa: BLE001 - the image still landed
                logger.exception("Could not build the label object")
        if item.notes:
            self._set_notes(slide, item.notes)

    @staticmethod
    def _content_placeholder(shapes):
        """The layout's content area for the picture: (shape, frame)
        or (None, None).

        Dragging an image onto a template slide by hand fits it to the
        content placeholder's frame; the send must land in the same
        frame or the deck reads mis-sized next to hand-placed slides.
        Only image-friendly placeholder types count; the largest wins
        when a layout offers several. A blank generic slide simply has
        none — the caller then falls back to fitting the whole slide.

        The frame (left, top, width, height) is captured during the
        scan — the placeholder IS the designed frame, filled edge to
        edge on the fitting axis — so the caller never re-reads the
        rect over COM.
        """

        best, best_frame, best_area = None, None, 0.0
        try:
            placeholders = shapes.Placeholders
            for index in range(1, int(placeholders.Count) + 1):
                shape = placeholders(index)
                kind = int(shape.PlaceholderFormat.Type)
                if kind not in CONTENT_PLACEHOLDER_TYPES:
                    continue
                width = float(shape.Width)
                height = float(shape.Height)
                if width * height > best_area:
                    best, best_area = shape, width * height
                    best_frame = (
                        float(shape.Left), float(shape.Top), width, height,
                    )
        except Exception:  # noqa: BLE001 - odd templates must not kill the send
            logger.debug("Could not probe placeholders", exc_info=True)
        return best, best_frame

    def _place_picture(self, presentation, slide, source: Path):
        """Insert the picture the way a manual insert lands.

        The content placeholder is NEVER deleted (explicit user
        decision: the content object must survive, so deleting the
        image later restores the empty content area). Three paths:

        * The empty content placeholder ABSORBS AddPicture2 — the
          returned Shape IS the placeholder — and PowerPoint applies
          the placeholder's own fit, exactly like a manual insert.
          Hands off: touching the geometry afterwards would fight the
          placeholder's semantics (and a delete here destroyed the
          picture outright — "Shape.Left : Object does not exist").
        * No absorption but the layout HAS a content area: contain-fit
          the free-floating picture to the placeholder's frame.
        * No content area at all (blank generic slides, title-only
          layouts): fit PPT_IMAGE_FIT of the slide, centred.
        """

        shapes = slide.Shapes
        _, frame = self._content_placeholder(shapes)

        picture = shapes.AddPicture2(
            str(source.resolve()),
            MSO_FALSE,   # LinkToFile
            MSO_TRUE,    # SaveWithDocument (embed)
            0, 0, -1, -1,  # native size
            MSO_FALSE,   # Compress
        )
        try:
            if int(picture.Type) == MSO_SHAPE_TYPE_PLACEHOLDER:
                return picture  # absorbed: native placement stands
        except Exception:  # noqa: BLE001 - treat as a free shape
            logger.debug("Could not read the picture's shape type",
                         exc_info=True)
        try:
            picture.LockAspectRatio = MSO_TRUE
            if frame is not None:
                frame_left, frame_top, frame_w, frame_h = frame
            else:
                page_setup = presentation.PageSetup
                slide_w = float(page_setup.SlideWidth)
                slide_h = float(page_setup.SlideHeight)
                frame_w = slide_w * defaults.PPT_IMAGE_FIT
                frame_h = slide_h * defaults.PPT_IMAGE_FIT
                frame_left = (slide_w - frame_w) / 2
                frame_top = (slide_h - frame_h) / 2
            width = float(picture.Width)
            height = float(picture.Height)
            if width > 0 and height > 0 and frame_w > 0 and frame_h > 0:
                scale = min(frame_w / width, frame_h / height)
                # LockAspectRatio scales Height in step with Width.
                picture.Width = width * scale
                picture.Left = frame_left + (frame_w - float(picture.Width)) / 2
                picture.Top = frame_top + (frame_h - float(picture.Height)) / 2
        except Exception:  # noqa: BLE001 - an unfitted picture beats none
            logger.exception("Could not fit the picture to the slide")
        return picture

    def _place_label(self, slide, picture, spec: LabelSpec) -> None:
        """Build the native, editable label over the placed picture.

        Geometry mirrors the burned-in label: build_layout gives the
        plate's rect in image coordinates, which maps onto the picture's
        rect on the slide, so the object lands where the watermark would
        have been — but movable.

        The cells are TEXT BOXES, not a table, for two proven reasons:
        PowerPoint refuses to group a table with a shape (the label
        would never move as one object), and text boxes were the user's
        own suggestion for "an actual PPT object". Everything is
        grouped: plate + one key box + one value box per field.
        """

        layout = build_layout(spec)
        pic_left = float(picture.Left)
        pic_top = float(picture.Top)
        pic_w = float(picture.Width)
        pic_h = float(picture.Height)
        if spec.image_width <= 0 or spec.image_height <= 0:
            return

        # The one scale that maps image pixels onto slide points. Every
        # dimension — rect, FONT and border alike — must go through it:
        # the style's font_size is a pixel size against the 1536 px
        # reference, and using it raw as points renders text 2-4x too
        # big for the plate the geometry builds (measured).
        to_points = pic_w / spec.image_width

        left = pic_left + layout.x * to_points
        top = pic_top + (layout.y / spec.image_height) * pic_h
        width = max(1.0, layout.width * to_points)
        height = max(1.0, (layout.height / spec.image_height) * pic_h)
        font_points = max(1.0, layout.font_pixel_size * to_points)

        style = spec.style
        # One Shapes fetch feeds the plate, every text box and the
        # group — under COM each re-fetch is a marshalled round trip
        # plus a fresh dynamic-dispatch wrapper (was 4+2·cells per
        # label; the fetch-count test pins the bound).
        shapes = slide.Shapes
        plate = shapes.AddShape(
            MSO_SHAPE_ROUNDED_RECTANGLE, left, top, width, height
        )
        fill = plate.Fill
        fill.ForeColor.RGB = _rgb(style.background_color)
        fill.Transparency = max(
            0.0, min(1.0, 1.0 - style.background_opacity / 100.0)
        )
        line = plate.Line
        if style.border_thickness > 0:
            line.Visible = MSO_TRUE
            line.ForeColor.RGB = _rgb(style.border_color)
            line.Weight = max(0.25, layout.border_width * to_points)
        else:
            line.Visible = MSO_FALSE
        try:
            # Adjustment 1 is corner roundness as a fraction of half the
            # short side (0 = square, 0.5 = fully rounded). The layout's
            # radius is in image pixels, so express it proportionally.
            short = max(1.0, min(layout.width, layout.height))
            roundness = max(0.0, min(0.5, layout.radius / short))
            adjustments = plate.Adjustments
            try:
                adjustments[1] = roundness
            except TypeError:
                # Early binding: makepy generates NO __setitem__ for the
                # indexed propput — it exposes SetItem(Index, value)
                # instead. Without this fallback the set failed
                # silently and every plate shipped with PowerPoint's
                # DEFAULT roundness (user-reported as a larger corner
                # radius after the early-binding change).
                adjustments.SetItem(1, roundness)
        except Exception:  # noqa: BLE001 - cosmetic only, but LOUD:
            # a silent styling failure already shipped once.
            logger.warning("Could not set the plate corner radius",
                           exc_info=True)

        text_names = self._build_label_texts(
            shapes, spec, layout, pic_left, pic_top, pic_h, to_points,
            font_points,
        )

        try:
            selection = shapes.Range([plate.Name, *text_names])
            selection.Group()
        except Exception:  # noqa: BLE001 - ungrouped still works, just fiddlier
            logger.exception("Could not group the label object")

    def _build_label_texts(
        self, shapes, spec: LabelSpec, layout, pic_left, pic_top, pic_h,
        to_points, font_points,
    ) -> list[str]:
        """One text box per key/value zone, on the SAME geometry the
        burned-in label measures — inset by the label's padding rather
        than starting at the plate's edge, with keys and values aligned
        per the style's settings. A custom cell is one box spanning its
        whole cell. Each box is grown by the native margin it is given,
        so the text lands exactly on the zone while the box stays
        comfortable to grab and edit in PowerPoint.

        Boxes in one label differ only by geometry, text and alignment,
        so the first box per alignment carries the full styling build
        and becomes that alignment's prototype; every later box is a
        native Duplicate of it, which carries ALL formatting — the
        bullet suppression (b2e5aa6) included.
        """

        m = defaults.PPT_TEXT_MARGIN_PT
        style = spec.style
        key_align = _PP_ALIGNMENT.get(style.key_alignment, PP_ALIGN_LEFT)
        value_align = _PP_ALIGNMENT.get(style.value_alignment, PP_ALIGN_RIGHT)
        # Alignment -> the first, fully styled box built for it. Scoped
        # to this label: geometry and font scale are per picture.
        prototypes: dict[int, object] = {}

        def zone_box(laid, zone, alignment):
            left = pic_left + zone.x * to_points - m
            top = pic_top + (zone.y / spec.image_height) * pic_h - m
            width = zone.width * to_points + 2 * m
            height = (zone.height / spec.image_height) * pic_h + 2 * m
            prototype = prototypes.get(alignment)
            if prototype is not None and self._clone_supported is not False:
                try:
                    box = self._clone_text_box(
                        prototype, laid.text, left, top, width, height
                    )
                except Exception:  # noqa: BLE001 - fidelity over speed
                    # Once per send, not per box: one failed clone
                    # predicts the rest; every box the clone path
                    # skips is scratch-built below with full styling.
                    self._clone_supported = False
                    logger.warning(
                        "Could not clone a label text box; building the "
                        "rest of the send from scratch",
                        exc_info=True,
                    )
                else:
                    self._clone_supported = True
                    return box
            box = self._add_text_box(
                shapes, laid.text, alignment, left, top, width, height,
                font_points, style,
            )
            prototypes[alignment] = box
            return box

        names: list[str] = []
        for cell in layout.cells:
            if self._stop.is_set():
                # Between cells, not mid-box: Stop lands within a
                # fraction of a slide instead of waiting out a whole
                # label build.
                raise _SendStopped()
            if isinstance(cell, LaidCustom):
                names.append(zone_box(cell.text, cell.zone, PP_ALIGN_LEFT).Name)
                continue
            names.append(zone_box(cell.key, cell.key_zone, key_align).Name)
            names.append(
                zone_box(cell.value, cell.value_zone, value_align).Name
            )
        return names

    @staticmethod
    def _clone_text_box(prototype, text, left, top, width, height):
        """A styled copy of the prototype at its own rect and text.

        Duplicate() copies the whole shape server-side in one call —
        TextFrame, font, paragraph format and the bullet suppression
        (b2e5aa6) ride along — so geometry and text are the only
        per-box writes. .Item(1), never [1]: the makepy ShapeRange
        exposes Item as a plain method (no Adjustments-style indexed
        propput), and dynamic dispatch resolves the same name.
        Geometry BEFORE text: Duplicate lands the copy offset from
        the prototype, and the one layout pass the Text write
        triggers must measure against the final rect.
        """

        dup_range = prototype.Duplicate()
        try:
            clone = dup_range.Item(1)
            clone.Left = left
            clone.Top = top
            clone.Width = width
            clone.Height = height
            clone.TextFrame.TextRange.Text = text
        except Exception:
            # A half-placed copy must not linger on the slide; the
            # caller rebuilds this box from scratch.
            try:
                dup_range.Delete()
            except Exception:  # noqa: BLE001 - best effort
                logger.exception("Could not remove a failed clone")
            raise
        return clone

    @staticmethod
    def _add_text_box(
        shapes, text, alignment, left, top, width, height, font_points, style
    ):
        box = shapes.AddTextbox(
            MSO_TEXT_ORIENTATION_HORIZONTAL, left, top, width, height
        )
        frame = box.TextFrame
        try:
            # BEFORE the text lands: templates default new boxes to
            # auto-fit + wrap, so every text/font set below would
            # trigger a PowerPoint re-measure and reflow — ~10 wasted
            # layout passes per box when these came last (measured).
            # Same end state, far less PowerPoint-side work.
            frame.AutoSize = PP_AUTOSIZE_NONE
            frame.WordWrap = MSO_FALSE
            frame.VerticalAnchor = defaults.PPT_TEXT_VERTICAL_ANCHOR
            # The box is grown by this same margin at creation, so the
            # text still lands on the layout's zone geometry.
            frame.MarginLeft = defaults.PPT_TEXT_MARGIN_PT
            frame.MarginRight = defaults.PPT_TEXT_MARGIN_PT
            frame.MarginTop = defaults.PPT_TEXT_MARGIN_PT
            frame.MarginBottom = defaults.PPT_TEXT_MARGIN_PT
        except Exception:  # noqa: BLE001 - cosmetic only, but loud:
            # styling failures must be visible in a default-level log.
            logger.warning("Could not pre-style a label text box",
                           exc_info=True)
        text_range = frame.TextRange
        text_range.Text = text
        font = text_range.Font
        font.Name = style.font_family
        font.Size = font_points
        font.Color.RGB = _rgb(style.font_color)
        # Deterministic against deck themes: no inherited bold/italic.
        font.Bold = MSO_FALSE
        font.Italic = MSO_FALSE
        try:
            para = text_range.ParagraphFormat
            para.Alignment = alignment
            # Deterministic against deck templates whose default text
            # box carries a bulleted list style: label text is never
            # bulleted, and the bullet's hanging indent must not shift
            # the text off the zone geometry.
            para.Bullet.Visible = MSO_FALSE
            level = frame.Ruler.Levels(1)
            level.FirstMargin = 0
            level.LeftMargin = 0
            box.Fill.Visible = MSO_FALSE
            box.Line.Visible = MSO_FALSE
        except Exception:  # noqa: BLE001 - cosmetic only, but loud:
            # this block carries the bullet suppression (b2e5aa6) —
            # a silent failure here corrupts labels against bulleted
            # templates with nothing in the log.
            logger.warning("Could not style a label text box", exc_info=True)
        return box

    def _set_notes(self, slide, notes: str) -> None:
        if self._notes_supported is False:
            return
        try:
            slide.NotesPage.Shapes.Placeholders(2).TextFrame.TextRange.Text = notes
            self._notes_supported = True
        except Exception:  # noqa: BLE001 - blank layouts may lack the placeholder
            # Once per send, not per slide: the layout is uniform, so
            # the first failure predicts the rest — skip the chain
            # (NotesPage alone is ~7 marshalled calls a slide).
            self._notes_supported = False
            logger.debug("Could not write slide notes; skipping for the "
                         "rest of the send", exc_info=True)
