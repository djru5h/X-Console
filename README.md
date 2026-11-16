# X-Console

A console-style channel strip VST2 for Akai MPC standalone (MPC OS 3.10.1+, Gen 2 / aarch64 such as the MPC XL).
Each strip is its own plugin with its own skin:

| Plugin | Tag | uid |
|---|---|---|
| X-Console: Flannel | `flannel` | XCN1 |
| X-Console: Granite | `granite` | XC4E |
| X-Console: Suede | `suede` | XCNV |
| X-Console: Hearts | `hearts` | XCWS |
| X-Console: Sandstone | `sandstone` | XCSM |
| X-Console: Hexx | `hexx` | XCAP |
| X-Console: Molten | `molten` | XCCH |
| X-Console: Spades | `spades` | XCAV |
| X-Console: Mocha | `mocha` | XC61 |
| X-Console: Titanium | `titanium` | XCTP |

Every strip has the same sections: preamp, filters, transient shaper and gate, a 4-band EQ with a live curve and
spectrum, compressor, drive, width and pan, and a gain-staging noise generator. The engine also holds two extra
models, TITANIUM EQ and TITANIUM DRIVE, that only an all-presets build offers.

## What's here

| Path | What it is |
|---|---|
| `src/` | The DSP engine (C): `xconsole.c`, the parameter table, the spectrum and the noise generator |
| `harness/` | Desktop test harness, demo renders and a CPU bench (`harness/run.sh`, Docker `gcc:12`) |
| `vst/` | Plugin config (`vst.json`), the skin generators (`vst/art/make_layout.py`, `make_art.py`), the default colours file, and one `vst/gen2-<tag>/` folder per strip with its `vst.json` and presets |
| `tools/` | The build scripts (`plugins.sh`, `colours-rebuild.sh`, `single-preset-build.sh`), the per-strip text settings (banner names, INFO text, knob colours, preset order), and the presets |
| `tools/custom-pages/` | The brushed-metal page generators (`<tag>/metal_pages.py` and the shared `metal_*.py`, `xc_logo.py`, `fixed_light.py`) with their page layouts |

## Building

X-Console builds on the [mpc-vst-plugins](https://github.com/djru5h/mpc-vst-plugins) framework (branch `ru5h-local`),
in WSL or Linux as root, with Docker:

```sh
tools/plugins.sh build all        # or one or more tags: tools/plugins.sh build flannel hexx
tools/plugins.sh list
```

The scripts expect three folders, set at the top of each script: the source (`X=/root/mpc-dev/mpc-xconsole`), the
framework (`MV=/root/mpc-dev/mpc-vst-plugins`) and a working folder for colours, pictures and build output (`P=`).
Change them to match your machine. The skin step uses the framework's `mpc-vst-html-art` Docker image, and the metal
pages a Python venv with Pillow and NumPy (`/root/venv-skin`). Each build writes
`<working folder>/gen2/<name>-<version>-mpc-aarch64.zip`.

The engine on its own:

```sh
harness/run.sh                    # sanitizer build, demos in harness/out, bench
```

## Not included

- **No maker logos, product screenshots or photos.** The build skips a logo whose picture isn't there. To show your
  own picture behind an EQ screen or curve, set `EQ PICTURE` / `CURVE PICTURE` / `PAGE PICTURE` in the colours file.
- The knob caps cut from photos (`real_caps.py` photo styles) need reference photos you supply yourself.
- Generated art, layouts and build output: the build makes them.
- The Theme Editor.

## Trademarks

The source comments and INFO pages name the hardware each strip is modelled on, to describe the design. Those names
are trademarks of their owners. X-Console isn't affiliated with or endorsed by any of them.

## Licence

MIT, see [LICENSE](LICENSE).
