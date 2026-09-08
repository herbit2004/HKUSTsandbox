# HKUST interior photograph reference package

Checked: 2026-09-05. Manifest: `/tmp/hkust-interior-photo-references.json`.

87 official image files downloaded and visually checked. The manifest contains 60 usable interior reference records, 11 tiny scene-identification thumbnails, exterior/event pictures excluded from interior inference, and one incorrect Atrium cubeface excluded after inspection. 17 supplementary i-Village/GGT downloads failed and remain explicitly unavailable. Every downloaded image has source URLs, dimensions and SHA-256. No AI-generated pictures are included.

## Use these first

| Files | Building / space | Modeling value | Corresponding plans |
|---|---|---|---|
| `shaw-01`–`shaw-05` | Shaw main hall and foyer | Light wood floors, vertical wood slats, white curved walls, green upholstered wood seats, black stage technical ceiling, suspended wood reflectors; hall modes must remain alternatives | `plans/shaw-floorplans-20250609.pdf`, `plans/shaw-stage-20241029.pdf`, `plans/shaw-seating-202504.pdf` |
| `libstudy-01`–`libstudy-21` | Lee Shau Kee Library rooms and common areas | Entries identify room/floor where supported; includes LG5, LC, quiet/group study and teaching rooms. Garden/terrace entries are marked exterior | Six floor plan PNGs in `plans/` |
| `libstudy-14.png` | Library LG5 | Black exposed ceiling, suspended lime/yellow/white polygon acoustic panels, green branching ceiling/column elements, gray herringbone carpet, pale wood wheeled tables, purple/black chairs and blue window-side seating | `plans/library-lg5.png` |
| `ivillage-01.jpg`–`ivillage-07.jpg` | i-Village double/single model rooms, cluster common space, kitchen, laundry A | White/gray fitted beds/storage/desks with blue chairs; dark gray common-area floor and exposed services ceiling. These rooms differ visibly from the generic old student-room VR | Public floor layout absent; do not infer hidden room dimensions |
| `ivillage-11.jpg`–`ivillage-14.jpg` | i-Village 7F living lounge / co-working | Yellow walls/columns, orange chairs, gray sofas, wood-like floors, turquoise glass; co-working white desks, black chairs and white exposed services | Official hall page specifies 7F common facilities; precise camera/plan registration unresolved |
| `innovation-05.jpg`–`innovation-07.jpg` | Martin Ka Shing Lee Innovation Building | Lab-view corridor; 5F InnoBay common area with white ceiling baffles, curved light and mint chairs; white/mint feature wall. Only photo 06 is explicitly labeled 5F | No full public floor plan obtained |
| `cyt-06.jpg`–`cyt-08.jpg` | Cheng Yu Tung Building | Double-height glass/wood lobby; open laboratory benches and write-up desk space. Room/floor unknown | No exact room plan obtained |

41 reference photographs in the priority groups above are marked `use_for_interior_model: true`. Other downloaded images have explicit inclusion/exclusion flags; inspect those flags rather than taking every image as an indoor scene.

## Teaching panoramas

The package also includes 20 horizontal cubemap faces for Atrium, academic concourse 1F/2F, a generic lecture theater and a generic undergraduate bedroom. The lecture theater letter/room and the bedroom hall/floor are unidentified. The generic wood-finish bedroom must not be used as an i-Village room.

The parent coordinator reports a newer teaching-photo package at `/tmp/hkust-teaching-interior-photos/`, with corrected Atrium `panoramas/Atrium/tile-composite-{f,r,b,l,u,d}.png` images. Prefer that agent's full panorama/coordinate manifest for the teaching building. The source `cube-Atrium-f.jpg` in this package is an unrelated sunset image served at the official URL and is explicitly excluded. This researcher has not independently reviewed the replacement composites.

## Evidence boundaries and attribution

All photography capture dates are unverified and remain null. Date-like filenames/upload directories are only clues; a current official page does not establish a current photography date. Floor and room associations are annotated individually, including uncertain ones. Photographs constrain visible materials, furniture and spatial relationships, not concealed walls or metric dimensions. The plan references establish building/floor association; camera positions and image-to-plan geometric registration have not been solved.

Images and plans remain attributable to HKUST and the linked source department: Library, Shaw Auditorium, CDO, SHRL or MTPC. Retain the manifest's source links. Public access is not evidence of an open redistribution license.

The main manifest embeds the nine downloaded plan sources and twelve official Matterport tour links. The Matterport tours were collected from the official MTPC page but not inspected, and have no local screenshots. Buildings/status research is in `/tmp/hkust-buildings.json` and `/tmp/hkust-buildings-research.md`.
