# TFS Label Maker

<!-- Full documentation: https://<site>/scripts/tfs_label_maker/ (enable this link when the site is live) -->

A PySide6/QML desktop utility that reads the metadata in `.tif` and `.png` images from a Thermo Scientific SEM-FIB microscope and builds a customizable label from the selected fields. Labels can be exported as `.svg` files, burned into a copy of the original image, or both, for single images or batches. Images and labels can also be sent to an active PowerPoint presentation.

## Features

- **Load images** by dragging them onto Catbug or with the Load button; process one image or a batch.
- **Metadata panel** with a searchable tree of the image's TFS metadata; check the fields to include in the label.
- **Label preview** with live styling: font, colors, position, and layout settings persist between sessions.
- **Output options**: label as `.svg`, label burned into a copy of the image, or both, saved to a timestamped `labelled_images/` folder in the script root.
- **Send to PowerPoint**: export images with or without labels directly into the active presentation.

## Requirements

- Python 3.11+
- PySide6 6.7.1+
- tifffile 2025.3.13+
- Pillow 10.1+
- NumPy 2.2.5+
- pywin32 306+ (Windows only, optional; needed for the PowerPoint export)

AutoScript is not required. All packages above ship with the AutoScript 4.14 Python environment, where the script is developed and tested, so no extra installation is needed there.

## Installation

1. Download the latest release ZIP from the [Releases page](https://github.com/ChrisLeeThompson/TFS_Label_Maker/releases).
2. Extract it and copy the script folder to your desired location. The script does not connect to a microscope, so it can be installed on any PC that meets the requirements.
3. If you run the script with the AutoScript Python environment, no packages need to be installed. Otherwise, install them with:

   ```
   pip install -r requirements.txt
   ```

## Running

Run the main module from the script folder:

```
python tfs_label_maker.py
```

The script also runs from the AutoScript Python interpreter or AutoScript Runner. Pass `--verbose` to log at DEBUG level, or `--log-file PATH` to also write the log to a file.

## Notes

- Exporting to an active PowerPoint presentation is Windows-only. Without pywin32, the PowerPoint card disables itself and the rest of the app runs normally.
- Label styling and output settings are stored in the Windows registry and persist between sessions and updates.

## License

MIT, see [LICENSE](LICENSE). Copyright (c) 2026 Christopher Thompson.

The Catbug artwork in `qml_resources/assets/` is not covered by the MIT license; see [LICENSE](LICENSE). PySide6 (Qt for Python) is licensed under the LGPLv3 and is used as an unmodified runtime dependency installed from PyPI; it is not distributed with this source.

## Contact

Developed by Chris Thompson with assistance from Anthropic's Claude. Questions and suggestions are welcome: [@ChrisLeeThompson](https://github.com/ChrisLeeThompson) on GitHub.
