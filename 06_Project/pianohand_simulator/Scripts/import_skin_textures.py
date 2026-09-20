"""Import the baked skin maps from Textures/*.png into /Game/PianoHand/Textures.

Run inside the editor (after Tools/bake_skin_maps.py has produced the PNGs):
    exec(open(r'C:/Git/PianoHandSimulator/06_Project/pianohand_simulator/Scripts/import_skin_textures.py').read())

Compression settings matter here:
  T_PH_SkinDetail_N  TC_Normalmap            BC5, two channels, z reconstructed - the right format
                                             for a pure tangent-space normal.
  T_PH_Vein_N        TC_VectorDisplacementmap RGBA8 uncompressed. BC5 would throw the alpha away and
                                             the alpha IS the vein mask.
  T_PH_WrinkleMask   TC_VectorDisplacementmap RGBA8 uncompressed, and NOT tiling (mesh UV space).
                                             Block compression would smear the direction channels,
                                             and a wrong direction reads as creases running the
                                             wrong way across the finger.
All three are linear - none of them is colour.
"""
import unreal, os

SRC_DIR = r'C:/Git/PianoHandSimulator/06_Project/pianohand_simulator/Textures'
DST = '/Game/PianoHand/Textures'

SETTINGS = {
    'T_PH_SkinDetail_N': dict(comp=unreal.TextureCompressionSettings.TC_NORMALMAP,
                              srgb=False, tiling=unreal.TextureAddress.TA_WRAP, flip_green=False),
    'T_PH_Vein_N':       dict(comp=unreal.TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP,
                              srgb=False, tiling=unreal.TextureAddress.TA_WRAP, flip_green=False),
    'T_PH_WrinkleMask':  dict(comp=unreal.TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP,
                              srgb=False, tiling=unreal.TextureAddress.TA_CLAMP, flip_green=False),
}

eal = unreal.EditorAssetLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
if not eal.does_directory_exist(DST):
    eal.make_directory(DST)

tasks = []
for name in SETTINGS:
    png = os.path.join(SRC_DIR, name + '.png')
    if not os.path.exists(png):
        print('MISSING', png)
        continue
    t = unreal.AssetImportTask()
    t.set_editor_property('filename', png)
    t.set_editor_property('destination_path', DST)
    t.set_editor_property('destination_name', name)
    t.set_editor_property('automated', True)
    t.set_editor_property('replace_existing', True)
    t.set_editor_property('save', True)
    tasks.append(t)

tools.import_asset_tasks(tasks)

for name, cfg in SETTINGS.items():
    path = DST + '/' + name
    tex = unreal.load_asset(path)
    if tex is None:
        print('import failed:', path)
        continue
    tex.set_editor_property('compression_settings', cfg['comp'])
    tex.set_editor_property('srgb', cfg['srgb'])
    tex.set_editor_property('address_x', cfg['tiling'])
    tex.set_editor_property('address_y', cfg['tiling'])
    if cfg['comp'] == unreal.TextureCompressionSettings.TC_NORMALMAP:
        tex.set_editor_property('flip_green_channel', cfg['flip_green'])
    unreal.EditorAssetLibrary.save_loaded_asset(tex)
    print('%-20s %dx%d  %s  srgb=%s' % (name, tex.blueprint_get_size_x(), tex.blueprint_get_size_y(),
                                        cfg['comp'], cfg['srgb']))
