bl_info = {
    "name": "Asset Collection Creator",
    "author": "VMakarchuk",
    "version": (3, 0),
    "blender": (4, 5, 0),
    "location": "3D View > N-Panel > Assets",
    "description": "Creates collection hierarchy, renames data, adds modifiers, applies transforms, purges orphan data, clears animation, and renames materials based on object names",
    "category": "Object",
}

import bpy
import os
import shutil
import bmesh
from mathutils import Vector
from bpy.props import FloatProperty, BoolProperty
import math
import glob

class MoveTexturesOperator(bpy.types.Operator):
    """Move all used textures into 'textures' folder next to .blend and make paths relative"""
    bl_idname = "object.move_all_textures"
    bl_label = "Move All Textures"

    def execute(self, context):
        blend_path = bpy.data.filepath
        if not blend_path:
            self.report({'ERROR'}, "Save the .blend file before running this")
            return {'CANCELLED'}

        # Папка textures рядом с .blend
        blend_dir = os.path.dirname(blend_path)
        textures_dir = os.path.join(blend_dir, "textures")
        if not os.path.exists(textures_dir):
            os.makedirs(textures_dir)

        moved_count = 0
        for img in bpy.data.images:
            if img.source == 'FILE' and img.filepath:
                abs_path = bpy.path.abspath(img.filepath)
                if os.path.exists(abs_path):
                    filename = os.path.basename(abs_path)
                    target_path = os.path.join(textures_dir, filename)

                    # Копируем, если это не тот же файл
                    if os.path.abspath(abs_path) != os.path.abspath(target_path):
                        try:
                            shutil.copy2(abs_path, target_path)
                            moved_count += 1
                        except Exception as e:
                            self.report({'WARNING'}, f"Failed to copy {filename}: {e}")

                    # Делаем путь относительным
                    img.filepath = bpy.path.relpath(target_path)

        self.report({'INFO'}, f"Moved {moved_count} textures to 'textures' folder and made paths relative")
        return {'FINISHED'}

class ReplaceTexturePathsOperator(bpy.types.Operator):
    """Replace all texture paths to //textures/..."""
    bl_idname = "images.replace_texture_paths"
    bl_label = "Replace Texture Paths"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        count = 0

        for img in bpy.data.images:
            if not img.filepath:
                continue

            path_str = img.filepath.replace("\\", "/")

            if "textures/" in path_str:
                after = path_str.split("textures/", 1)[1]
                new_rel = f"//textures/{after}"

                if new_rel != img.filepath:
                    img.filepath = new_rel
                    count += 1
                    print(f"{img.name}\n  {path_str}\n  -> {new_rel}\n")

        def draw_popup(self, context):
            self.layout.label(text=f"Replaced paths: {count}")

        context.window_manager.popup_menu(draw_popup, title="Done", icon='INFO')

        self.report({'INFO'}, f"Replaced paths: {count}")
        return {'FINISHED'}

def rename_materials_by_object():
    renamed_count = 0
    for obj in bpy.data.objects:
        if obj.material_slots:
            for slot in obj.material_slots:
                if slot.material:
                    target_name = obj.name
                    if not target_name.endswith("Material"):
                        target_name += "Material"
                    if slot.material.name != target_name:
                        slot.material.name = target_name
                        renamed_count += 1
    return renamed_count


class SimpleAssetNameInput(bpy.types.Operator):
    """Create a clean asset hierarchy with collections and naming conventions.
        - Creates a root collection named after the asset
        - Adds _main and _geo sub-collections
        - Renames all objects in the scene with the asset name prefix
        - Renames mesh data blocks to follow the *ObjectNameShape* convention
        - Adds or updates a Subdivision modifier (levels = 1, render = 2)
        - Moves all objects into the _geo collection"""
    bl_idname = "object.simple_asset_name_input"
    bl_label = "Create Asset Collections"

    asset_name: bpy.props.StringProperty(name="Asset Name")

    def invoke(self, context, event):
        filename = os.path.splitext(os.path.basename(bpy.data.filepath))[0]
        self.asset_name = filename.capitalize() if filename else "AssetName"
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        self.asset_name = self.asset_name.capitalize()

        if self.asset_name in bpy.data.collections:
            self.report({'WARNING'}, f"Hierarchy '{self.asset_name}' already exists")
            return {'CANCELLED'}

        def create_collection(name, parent=None):
            coll = bpy.data.collections.new(name)
            if parent:
                parent.children.link(coll)
            else:
                bpy.context.scene.collection.children.link(coll)
            return coll

        #coll_asset = create_collection(self.asset_name)
        coll_main = create_collection(f"{self.asset_name}_main")
        coll_geo = create_collection(f"{self.asset_name}_geo", coll_main)

        for obj in list(bpy.context.scene.objects):
            # Check if object name starts with asset name (case-insensitive)
            if obj.name.lower().startswith(self.asset_name.lower() + "_"):
                correct_prefix = self.asset_name + "_"
                if not obj.name.startswith(correct_prefix):
                    obj.name = correct_prefix + obj.name[len(correct_prefix):]
            else:
                obj.name = f"{self.asset_name}_{obj.name}"

            # Rename mesh data
            if obj.type == 'MESH' and obj.data:
                if not obj.data.name.endswith("Shape"):
                    obj.data.name = obj.name + "Shape"

            # Add or update Subdivision modifier
            subsurf = obj.modifiers.get("Subdivision")
            if not subsurf:
                subsurf = obj.modifiers.new("Subdivision", 'SUBSURF')
            subsurf.levels = 1
            subsurf.render_levels = 2
            subsurf.show_in_editmode = True
            subsurf.show_on_cage = True

            # Move object to the geo collection
            for c in obj.users_collection:
                c.objects.unlink(obj)
            coll_geo.objects.link(obj)

        self.report({'INFO'}, f"Created asset hierarchy: {self.asset_name}")
        return {'FINISHED'}


class ApplyAllTransformsOperator(bpy.types.Operator):
    """Apply location, rotation, and scale to all objects"""
    bl_idname = "object.apply_all_transforms"
    bl_label = "Apply All Transforms"

    def execute(self, context):
        bpy.ops.object.select_all(action='DESELECT')
        for obj in bpy.data.objects:
            if obj.type in {'MESH', 'CURVE', 'SURFACE', 'META', 'FONT'}:
                obj.select_set(True)
        bpy.context.view_layer.objects.active = context.selected_objects[0] if context.selected_objects else None
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        self.report({'INFO'}, "Applied transforms to all objects")
        return {'FINISHED'}
        
class ShadeSmoothAllOperator(bpy.types.Operator):
    """Set Shade Smooth for all objects"""
    bl_idname = "object.shade_smooth_all"
    bl_label = "Shade Smooth All"

    def execute(self, context):
        bpy.ops.object.select_all(action='DESELECT')
        mesh_objects = [obj for obj in bpy.data.objects if obj.type == 'MESH']
        for obj in mesh_objects:
            obj.select_set(True)
        if mesh_objects:
            bpy.context.view_layer.objects.active = mesh_objects[0]
            bpy.ops.object.shade_smooth()
        self.report({'INFO'}, "Shade Smooth applied to all mesh objects")
        return {'FINISHED'}


class ClearAnimationOperator(bpy.types.Operator):
    """Clear all animation data from scene"""
    bl_idname = "object.clear_animation"
    bl_label = "Clear Animation"

    def execute(self, context):
        data_blocks = (
            list(bpy.data.objects)
            + list(bpy.data.materials)
            + list(bpy.data.meshes)
            + list(bpy.data.cameras)
            + list(bpy.data.lights)
            + list(bpy.data.curves)
            + list(bpy.data.armatures)
        )
        cleared = 0
        for datablock in data_blocks:
            if datablock.animation_data:
                datablock.animation_data_clear()
                cleared += 1

        self.report({'INFO'}, f"Cleared animation from {cleared} datablocks")
        return {'FINISHED'}


class PurgeOrphansOperator(bpy.types.Operator):
    """Purge orphan (unused) datablocks"""
    bl_idname = "object.purge_orphans"
    bl_label = "Purge Orphan Data"

    def execute(self, context):
        bpy.ops.outliner.orphans_purge(
            do_local_ids=True,
            do_linked_ids=True,
            do_recursive=True
        )
        self.report({'INFO'}, "Purged orphan data")
        return {'FINISHED'}


class RenameAllMaterialsOperator(bpy.types.Operator):
    """Rename all materials to match their object's name + 'Material'"""
    bl_idname = "object.rename_all_materials"
    bl_label = "Rename All Materials"

    def execute(self, context):
        renamed_count = rename_materials_by_object()
        self.report({'INFO'}, f"Renamed {renamed_count} materials")
        return {'FINISHED'}

class CreateRigOperator(bpy.types.Operator):
    """Create an Armature in the asset hierarchy"""
    bl_idname = "object.create_rig"
    bl_label = "Create Rig"

    asset_name: bpy.props.StringProperty(name="Asset Name")

    def invoke(self, context, event):
        import os
        # Default name = filename or "AssetName"
        filename = bpy.path.basename(bpy.data.filepath)
        default_name = os.path.splitext(filename)[0] if filename else "AssetName"
        self.asset_name = default_name.capitalize()
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        self.asset_name = self.asset_name.capitalize()

        # Find the _main collection
        coll_main = bpy.data.collections.get(f"{self.asset_name}_main")
        if not coll_main:
            self.report({'ERROR'}, f"Collection {self.asset_name}_main not found. Create Asset Collections first.")
            return {'CANCELLED'}

        # Create rig object
        bpy.ops.object.armature_add(enter_editmode=False)
        rig_obj = context.active_object

        # Переименовываем и объект, и саму арматуру (data)
        rig_obj.name = f"{self.asset_name}_rig"
        rig_obj.data.name = f"{self.asset_name}_armature"

        # Disable from render immediately
        rig_obj.hide_render = True

        # Move armature to _main
        for c in rig_obj.users_collection:
            c.objects.unlink(rig_obj)
        coll_main.objects.link(rig_obj)

        self.report({'INFO'}, f"Created rig: {rig_obj.name}")
        return {'FINISHED'}


class SceneCheckOperator(bpy.types.Operator):
    """Check scene"""
    bl_idname = "object.scene_check_operator"
    bl_label = "Scene Check"

    def execute(self, context):
        results = []
        all_ok = True

        
        #_geo is not selectable
        geo_collections = [c for c in bpy.data.collections if c.name.endswith("_geo")]

        for coll_geo in geo_collections:
            if coll_geo.hide_select:
                results.append(f"[OK] {coll_geo.name} is not selectable")
            else:
                results.append(f"[FAIL] {coll_geo.name} must be not selectable (hide_select=True)")
                all_ok = False


        # --- Popup with full report
        message = "\n".join(results)

        def draw(self_popup, _context):
            for line in message.split("\n"):
                icon = 'CHECKMARK' if line.startswith("[OK]") else ('ERROR' if line.startswith("[FAIL]") else 'INFO')
                self_popup.layout.label(text=line, icon=icon)

        context.window_manager.popup_menu(draw, title="Rig Check", icon='ARMATURE_DATA')

        return {'FINISHED' if all_ok else 'CANCELLED'}


class OBJECT_OT_rename_asset_armature(bpy.types.Operator):
    bl_idname = "object.rename_asset_armature"
    bl_label = "Переименовать _armature"

    old_name: bpy.props.StringProperty()
    new_name: bpy.props.StringProperty()

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=360)

    def draw(self, context):
        self.layout.label(text=f"Изменить {self.old_name} на {self.new_name}?")

    def execute(self, context):
        armature_data = bpy.data.armatures.get(self.old_name)
        if armature_data is None:
            self.report({'WARNING'}, f"Armature data {self.old_name} не найдена")
            return {'CANCELLED'}
        armature_data.name = self.new_name
        self.report({'INFO'}, f"{self.old_name} -> {self.new_name}")
        bpy.ops.object.rig_check_operator()
        return {'FINISHED'}


class RigCheckOperator(bpy.types.Operator):
    """Check asset & rig structure without stopping on first failure"""
    bl_idname = "object.rig_check_operator"
    bl_label = "Rig Check"

    def execute(self, context):
        results = []
        all_ok = True
        armature_rename_request = None

        scene_root = context.scene.collection

        # --- Find asset root under Scene Collection by pattern:
        # root "<AssetName>_main" under Scene Collection
        asset_root = None
        coll_main = None
        for root in scene_root.children:
            if root.name.endswith("_main"):
                asset_root = root
                break

        if asset_root is None:
            self.report({'ERROR'}, "Asset root not found. Expected: <AssetName>_main under Scene Collection.")
            return {'CANCELLED'}

        # Убираем _main для получения asset_name
        asset_name = asset_root.name[:-5]  # срезаем "_main"
        coll_main = asset_root
        # --- Check <AssetName>_main is inside <AssetName>
        results.append(f"[OK] Found {asset_name}_main inside {asset_name}")

        # --- Check <AssetName>_geo inside <AssetName>_main and not selectable
        geo_name = f"{asset_name}_geo"
        coll_geo = next((c for c in coll_main.children if c.name == geo_name), None)
        if coll_geo:
            results.append(f"[OK] Found {geo_name} inside {asset_name}_main")
            if coll_geo.hide_select:
                results.append(f"[OK] {geo_name} is not selectable")
            else:
                results.append(f"[FAIL] {geo_name} must be not selectable (hide_select=True)")
                all_ok = False
        else:
            results.append(f"[FAIL] {geo_name} missing or not inside {asset_name}_main")
            all_ok = False

        # --- Check rig object <AssetName>_rig (ARMATURE) inside <AssetName>_main and hidden in render,  selectable,  visible in viewport
        rig_name = f"{asset_name}_rig"
        rig_obj = next((o for o in coll_main.objects if o.name == rig_name), None)
        if rig_obj and rig_obj.type == 'ARMATURE':
            results.append(f"[OK] Rig found: {rig_name} in {asset_name}_main")
            if rig_obj.hide_render:
                results.append(f"[OK] {rig_name} is hidden in render")
            else:
                results.append(f"[FAIL] {rig_name} should be hidden in render (hide_render=True)")
                all_ok = False
            
            # Check selectable
            if not rig_obj.hide_select:
                results.append(f"[OK] {rig_name} is selectable")
            else:
                results.append(f"[FAIL] {rig_name} should be selectable (hide_select=False)")
                all_ok = False
            
            # Check visible in viewport (monitor icon)
            if not rig_obj.hide_viewport:
                results.append(f"[OK] {rig_name} is visible in viewport (monitor)")
            else:
                results.append(f"[FAIL] {rig_name} should be visible in viewport (hide_viewport=False)")
                all_ok = False
            
            # Check visible (eye icon)
            if not rig_obj.hide_get():
                results.append(f"[OK] {rig_name} is visible (eye icon)")
            else:
                results.append(f"[FAIL] {rig_name} should be visible (hide_get() should return False)")
                all_ok = False

            expected_armature_data_name = f"{asset_name}_armature"
            current_armature_data_name = rig_obj.data.name if rig_obj.data else ""
            if current_armature_data_name == expected_armature_data_name:
                results.append(f"[OK] Found armature data {expected_armature_data_name}")
            elif current_armature_data_name:
                results.append(
                    f"[FAIL] Expected armature data {expected_armature_data_name}, found: {current_armature_data_name}"
                )
                all_ok = False
                armature_rename_request = (current_armature_data_name, expected_armature_data_name)
            else:
                results.append(f"[FAIL] armature data missing on {rig_name}")
                all_ok = False
        else:
            arm_in_main = [o.name for o in coll_main.objects if o.type == 'ARMATURE']
            if arm_in_main:
                results.append(f"[FAIL] Expected ARMATURE named {rig_name}, found: {', '.join(arm_in_main)}")
            else:
                results.append(f"[FAIL] No ARMATURE {rig_name} in {asset_name}_main")
            all_ok = False

            
        # --- Check names (objects, bones, collections) for non-English characters
        bad_names = []

        # объекты
        for obj in bpy.context.scene.objects:
            for ch in obj.name:
                if ord(ch) > 127:
                    bad_names.append(f"Object: {obj.name} (invalid char: '{ch}')")
                    break

            if obj.type == 'ARMATURE':
                # проверка костей
                for bone in obj.data.bones:
                    for ch in bone.name:
                        if ord(ch) > 127:
                            bad_names.append(f"Bone: {obj.name}:{bone.name} (invalid char: '{ch}')")
                            break

        # коллекции
        for coll in bpy.data.collections:
            for ch in coll.name:
                if ord(ch) > 127:
                    bad_names.append(f"Collection: {coll.name} (invalid char: '{ch}')")
                    break

        if bad_names:
            results.append("[FAIL] Non-English characters found in names:\n" + "\n".join(bad_names))
            all_ok = False
        else:
            results.append("[OK] All names use English characters only")
            

        # --- Check WGTS collection WGTS inside OR outside <AssetName>_main
        wgts_name = f"WGTS"

        # Try inside _main first
        wgts_coll = next((c for c in coll_main.children if c.name == wgts_name), None)
        wgts_location = "inside _main" if wgts_coll else None

        if wgts_coll:
            results.append(f"[OK] Found {wgts_name} {wgts_location}")
            
            # Проверка hide_render
            if wgts_coll.hide_render:
                results.append(f"[OK] {wgts_name} is hidden in render")
            else:
                results.append(f"[FAIL] {wgts_name} should be hidden in render (hide_render=True)")
                all_ok = False
            
            # Проверка hide_viewport
            if wgts_coll.hide_viewport:
                results.append(f"[OK] {wgts_name} is hidden in viewport (hide_viewport=True)")
            else:
                results.append(f"[FAIL] {wgts_name} should be hidden in viewport (hide_viewport=True)")
                all_ok = False
            
            # Проверка exclude (исключение из viewport)
            # Находим соответствующую layer_collection
            def find_layer_collection(layer_coll, name):
                if layer_coll.name == name:
                    return layer_coll
                for child in layer_coll.children:
                    found = find_layer_collection(child, name)
                    if found:
                        return found
                return None
            
            layer_coll = find_layer_collection(bpy.context.view_layer.layer_collection, wgts_name)
            
            if layer_coll:
                if layer_coll.exclude:
                    results.append(f"[OK] {wgts_name} is excluded from viewport")
                else:
                    results.append(f"[FAIL] {wgts_name} should be excluded from viewport (exclude=True)")
                    all_ok = False
            else:
                results.append(f"[WARNING] Could not find layer collection for {wgts_name}")
                
        else:
            results.append(f"[FAIL] {wgts_name} missing (expected inside {asset_name}_main)")
            all_ok = False

            
        # --- Check that all mesh objects belong to exactly one collection
        '''
        wrong_collections = []
        for obj in bpy.context.scene.objects:
            if obj.type == 'MESH' and not in_wgts_collection(obj):
                if len(obj.users_collection) != 1:
                    wrong_collections.append(
                        f"{obj.name} (found in {[c.name for c in obj.users_collection]})"
                    )

        if wrong_collections:
            results.append("[FAIL] Mesh objects must belong to exactly one collection:\n" + "\n".join(wrong_collections))
            all_ok = False
        else:
            results.append("[OK] All mesh objects belong to exactly one collection")
        '''
        
        # --- Check SQST_Lattice object
        sqst_name = "SQST_Lattice"
        sqst_obj = bpy.data.objects.get(sqst_name)

        if sqst_obj:
            results.append(f"[OK] Found {sqst_name}")
            
            # Проверка hide_render
            if sqst_obj.hide_render:
                results.append(f"[OK] {sqst_name} is hidden in render")
            else:
                results.append(f"[FAIL] {sqst_name} should be hidden in render (hide_render=True)")
                all_ok = False
            
            # Проверка hide_viewport
            if sqst_obj.hide_viewport:
                results.append(f"[OK] {sqst_name} is hidden in viewport (hide_viewport=True)")
            else:
                results.append(f"[FAIL] {sqst_name} should be hidden in viewport (hide_viewport=True)")
                all_ok = False
            
            if sqst_obj.hide_select:
                results.append(f"[OK] {sqst_name} is not selectable")
            else:
                results.append(f"[FAIL] {sqst_name} must be not selectable (hide_select=True)")
                all_ok = False
        else:
            results.append(f"[OK] {sqst_name} not present in scene (no check needed)")
        
        #Subdiv in viewport = 1
        wrong_subdivs = []
        for obj in bpy.context.scene.objects:
            if obj.type == 'MESH':
                for mod in obj.modifiers:
                    if mod.type == 'SUBSURF' and mod.levels != 1:
                        wrong_subdivs.append(
                            f"{obj.name} (modifier '{mod.name}' has viewport levels = {mod.levels})"
                        )

        if wrong_subdivs:
            results.append("[FAIL] Subdivision Surface modifiers must have 1 levels in viewport:\n" + "\n".join(wrong_subdivs))
            all_ok = False
        else:
            results.append("[OK] All Subdivision Surface modifiers are set to 1 in viewport")
        
        # Subdivision Surface must be the last modifier
        wrong_order_subdivs = []
        for obj in bpy.context.scene.objects:
            if obj.type == 'MESH':
                mods = obj.modifiers
                for i, mod in enumerate(mods):
                    if mod.type == 'SUBSURF':
                        # Если сабдив не последний
                        if i != len(mods) - 1:
                            # Проверим, что после него нет ещё одного сабдива (на случай нескольких)
                            after = [m.name for m in mods[i+1:]]
                            wrong_order_subdivs.append(
                                f"{obj.name} (modifier '{mod.name}' not last; after it: {', '.join(after)})"
                            )

        if wrong_order_subdivs:
            results.append("[FAIL] Subdivision Surface modifiers must be last in the stack:\n" + "\n".join(wrong_order_subdivs))
            all_ok = False
        else:
            results.append("[OK] All Subdivision Surface modifiers are last in their stacks")


        # --- Check for empty collections in the scene
        empty_colls = []
        for coll in bpy.data.collections:
            if not coll.objects and not coll.children:
                empty_colls.append(coll.name)

        if empty_colls:
            results.append("[FAIL] Empty collections found:\n" + "\n".join(empty_colls))
            all_ok = False
        else:
            results.append("[OK] No empty collections in the scene")
        
        # --- Check rotation mode of all pose bones (must be XYZ Euler)
        wrong_modes = []
        for obj in bpy.context.scene.objects:
            if obj.type == 'ARMATURE':
                for pbone in obj.pose.bones:
                    # --- пропускаем исключения
                    if pbone.name.startswith(("SQB", "SQST", "SQT")):
                        continue
                    if pbone.rotation_mode != 'XYZ':
                        wrong_modes.append(f"{obj.name}:{pbone.name} ({pbone.rotation_mode})")

        if wrong_modes:
            formatted = "\n".join(wrong_modes)
            results.append(f"[FAIL] Pose bones not in XYZ Euler:\n{formatted}")
            all_ok = False
        else:
            results.append("[OK] All pose bones in all armatures use XYZ Euler")
        
        # --- Check if all pose bones are reset (zeroed transforms)
        not_reset = []
        for obj in bpy.context.scene.objects:
            if obj.type == 'ARMATURE':
                for pbone in obj.pose.bones:
                    loc_ok = all(abs(v) < 1e-4 for v in pbone.location)
                    sca_ok = all(abs(v - 1.0) < 1e-4 for v in pbone.scale)

                    if pbone.rotation_mode == 'QUATERNION':
                        rot_ok = (
                            abs(pbone.rotation_quaternion.w - 1.0) < 1e-4 and
                            abs(pbone.rotation_quaternion.x) < 1e-4 and
                            abs(pbone.rotation_quaternion.y) < 1e-4 and
                            abs(pbone.rotation_quaternion.z) < 1e-4
                        )
                    else:  # Euler and other modes
                        rot_ok = all(abs(v) < 1e-4 for v in pbone.rotation_euler)

                    if not (loc_ok and sca_ok and rot_ok):
                        not_reset.append(f"{obj.name}:{pbone.name}")

        if not_reset:
            formatted = "\n".join(not_reset)
            results.append(f"[FAIL] Pose bones not reset to default:\n{formatted}")
            all_ok = False
        else:
            results.append("[OK] All pose bones are reset to default transforms")
        
        # --- Check if Root/Main pose bones local Y matches global Y
        wrong_orient = []
        for obj in bpy.context.scene.objects:
            if obj.type == 'ARMATURE':
                for pbone in obj.pose.bones:
                    if pbone.name.lower() not in ("root", "main"):
                        continue

                    # локальная ось Y в глобале
                    y_axis = (pbone.matrix.to_3x3() @ Vector((0, 1, 0))).normalized()

                    # угол между локальной Y и глобальной Y
                    angle = y_axis.angle(Vector((0, 1, 0)), 0.0)
                    deg = math.degrees(angle)

                    if deg > 0.1:  # допуск
                        wrong_orient.append(
                            f"{obj.name}:{pbone.name} → angle={deg:.2f}°, axis={tuple(round(v, 3) for v in y_axis)}"
                        )

        if wrong_orient:
            formatted = "\n".join(wrong_orient)
            results.append(f"[FAIL] Root/Main bones not aligned to global +Y:\n{formatted}")
            all_ok = False
        else:
            results.append("[OK] Root/Main bones aligned to global +Y")


        
        # --- Check for orphan data
        orphans = []

        # Проверяем основные типы данных
        for datablock_type, datablocks in {
            "Meshes": bpy.data.meshes,
            "Materials": bpy.data.materials,
            "Images": bpy.data.images,
            "Actions": bpy.data.actions,
            "Node Groups": bpy.data.node_groups,
            "Collections": bpy.data.collections,
        }.items():
            for datablock in datablocks:
                if datablock.users == 0:
                    orphans.append(f"{datablock_type}: {datablock.name}")

        if orphans:
            results.append("[FAIL] Orphan data blocks found:\n" + "\n".join(orphans))
            all_ok = False
        else:
            results.append("[OK] No orphan data found")
        
        # --- Check for missing images/textures
        missing_images = []
        for img in bpy.data.images:
            # Игнорируем встроенные (генерируемые Blender'ом)
            if img.source in {'GENERATED', 'VIEWER'}:
                continue

            if img.source == 'TILED':  # UDIM
                abs_path = bpy.path.abspath(img.filepath)
                if "<UDIM>" in abs_path:
                    # Проверяем, есть ли хоть один файл, соответствующий маске
                    udim_glob = abs_path.replace("<UDIM>", "[0-9][0-9][0-9][0-9]")
                    matches = glob.glob(udim_glob)
                    if not matches and not img.packed_file:
                        missing_images.append(f"{img.name} (UDIM)")
                else:
                    # Если вдруг UDIM, но нет <UDIM> в пути
                    if not os.path.exists(abs_path) and not img.packed_file:
                        missing_images.append(f"{img.name} (UDIM path broken)")

            else:
                # Обычные текстуры
                if not img.filepath or (not img.packed_file and not img.has_data):
                    missing_images.append(img.name)
                else:
                    abs_path = bpy.path.abspath(img.filepath)
                    if not os.path.exists(abs_path) and not img.packed_file:
                        missing_images.append(img.name)

        if missing_images:
            results.append(f"[FAIL] Missing or broken images: {', '.join(missing_images)}")
            all_ok = False
        else:
            results.append("[OK] No missing images/textures found")
            
        # --- Check 3D cursor location
        cursor_loc = bpy.context.scene.cursor.location
        if cursor_loc.x != 0.0 or cursor_loc.y != 0.0 or cursor_loc.z != 0.0:
            results.append(
                f"[FAIL] 3D Cursor must be at (0,0,0), current position: "
                f"({cursor_loc.x:.3f}, {cursor_loc.y:.3f}, {cursor_loc.z:.3f})"
            )
            all_ok = False
        else:
            results.append("[OK] 3D Cursor is at (0,0,0)")

        # --- Check 3D cursor rotation
        cursor_rot = bpy.context.scene.cursor.rotation_euler
        if cursor_rot.x != 0.0 or cursor_rot.y != 0.0 or cursor_rot.z != 0.0:
            results.append(
                f"[FAIL] 3D Cursor rotation must be (0,0,0), current rotation: "
                f"({cursor_rot.x:.3f}, {cursor_rot.y:.3f}, {cursor_rot.z:.3f})"
            )
            all_ok = False
        else:
            results.append("[OK] 3D Cursor rotation is (0,0,0)")


        # --- Check animation actions
        empty_actions = []
        unlinked_actions = []

        for action in bpy.data.actions:
            # --- Skip empty actions (no F-curves)
            if not action.fcurves:
                empty_actions.append(action.name)
                continue

            # --- Check if the action is not linked to any object
            if not action.users:
                unlinked_actions.append(action.name)

        if empty_actions:
            formatted = "\n".join(empty_actions)
            results.append(f"[FAIL] Empty actions (no F-curves):\n{formatted}")
            all_ok = False

        if unlinked_actions:
            formatted = "\n".join(unlinked_actions)
            results.append(f"[FAIL] Unlinked actions (no users):\n{formatted}")
            all_ok = False

        if all_ok:
            results.append("[OK] All actions have F-curves and are linked to objects")



        # --- Popup with full report
        message = "\n".join(results)

        def draw(self_popup, _context):
            for line in message.split("\n"):
                icon = 'CHECKMARK' if line.startswith("[OK]") else ('ERROR' if line.startswith("[FAIL]") else 'INFO')
                self_popup.layout.label(text=line, icon=icon)

        context.window_manager.popup_menu(draw, title="Rig Check", icon='ARMATURE_DATA')

        if armature_rename_request:
            bpy.ops.object.rename_asset_armature(
                'INVOKE_DEFAULT',
                old_name=armature_rename_request[0],
                new_name=armature_rename_request[1],
            )

        return {'FINISHED' if all_ok else 'CANCELLED'}
  
  
def in_wgts_collection(obj):
    return any(coll.name == "WGTS" for coll in obj.users_collection)


class ModelingCheckOperator(bpy.types.Operator):
    """Check modeling rules for assets"""
    bl_idname = "object.modeling_check_operator"
    bl_label = "Modeling Check"

    def execute(self, context):
        results = []
        all_ok = True
        
        scene_root = context.scene.collection

        # --- Find asset root under Scene Collection by pattern:
        # root "<AssetName>_main" under Scene Collection
        asset_root = None
        coll_main = None
        for root in scene_root.children:
            if root.name.endswith("_main"):
                asset_root = root
                break

        if asset_root is None:
            self.report({'ERROR'}, "Asset root not found. Expected: <AssetName>_main under Scene Collection.")
            return {'CANCELLED'}

        # Убираем _main для получения asset_name
        asset_name = asset_root.name[:-5]  # срезаем "_main"
        coll_main = asset_root
        # --- Check <AssetName>_main is inside <AssetName>
        results.append(f"[OK] Found {asset_name}_main inside {asset_name}")

        # --- Check <AssetName>_geo inside <AssetName>_main and not selectable
        def is_in_geo_collection(obj):
            """Проверяет, находится ли объект внутри любой коллекции,
               которая вложена в *_geo (включая промежуточные)."""

            def has_geo_parent(coll):
                if coll.name.endswith("_geo"):
                    return True
                # рекурсивно ищем родителей через bpy.data.collections
                for parent in bpy.data.collections:
                    if coll.name in parent.children.keys():
                        if has_geo_parent(parent):
                            return True
                return False

            for coll in obj.users_collection:
                if has_geo_parent(coll):
                    return True
            return False


        bad_hierarchy = []
        for obj in bpy.context.scene.objects:
            if obj.type == 'MESH' and not in_wgts_collection(obj):
                if not is_in_geo_collection(obj):
                    colls = [c.name for c in obj.users_collection]
                    bad_hierarchy.append(f"{obj.name} (current: {', '.join(colls)})")

        if bad_hierarchy:
            results.append("[FAIL] Objects outside *_geo collections:\n" + "\n".join(bad_hierarchy))
            all_ok = False
        else:
            results.append("[OK] All geometry objects are inside *_geo collections")
            
            
        # --- Check that all mesh objects belong to exactly one collection
        '''
        wrong_collections = []
        for obj in bpy.context.scene.objects:
            if obj.type == 'MESH' and not in_wgts_collection(obj):
                if len(obj.users_collection) != 1:
                    wrong_collections.append(
                        f"{obj.name} (found in {[c.name for c in obj.users_collection]})"
                    )

        if wrong_collections:
            results.append("[FAIL] Mesh objects must belong to exactly one collection:\n" + "\n".join(wrong_collections))
            all_ok = False
        else:
            results.append("[OK] All mesh objects belong to exactly one collection")
        '''
        # --- Check names (objects, bones, collections) for non-English characters
        bad_names = []

        # объекты
        for obj in bpy.context.scene.objects:
            for ch in obj.name:
                if ord(ch) > 127:
                    bad_names.append(f"Object: {obj.name} (invalid char: '{ch}')")
                    break

            if obj.type == 'ARMATURE':
                # проверка костей
                for bone in obj.data.bones:
                    for ch in bone.name:
                        if ord(ch) > 127:
                            bad_names.append(f"Bone: {obj.name}:{bone.name} (invalid char: '{ch}')")
                            break

        # коллекции
        for coll in bpy.data.collections:
            for ch in coll.name:
                if ord(ch) > 127:
                    bad_names.append(f"Collection: {coll.name} (invalid char: '{ch}')")
                    break

        if bad_names:
            results.append("[FAIL] Non-English characters found in names:\n" + "\n".join(bad_names))
            all_ok = False
        else:
            results.append("[OK] All names use English characters only")
            
            
        #Subdiv in viewport = 0
        wrong_subdivs = []
        for obj in bpy.context.scene.objects:
            if obj.type == 'MESH':
                for mod in obj.modifiers:
                    if mod.type == 'SUBSURF' and mod.levels != 1:
                        wrong_subdivs.append(
                            f"{obj.name} (modifier '{mod.name}' has viewport levels = {mod.levels})"
                        )

        if wrong_subdivs:
            results.append("[FAIL] Subdivision Surface modifiers must have 1 levels in viewport:\n" + "\n".join(wrong_subdivs))
            all_ok = False
        else:
            results.append("[OK] All Subdivision Surface modifiers are set to 1 in viewport")
            
            
        # --- Check for empty collections in the scene
        empty_colls = []
        for coll in bpy.data.collections:
            if not coll.objects and not coll.children:
                empty_colls.append(coll.name)

        if empty_colls:
            results.append("[FAIL] Empty collections found:\n" + "\n".join(empty_colls))
            all_ok = False
        else:
            results.append("[OK] No empty collections in the scene")

        # --- Check that all mesh objects have applied transforms
        wrong_transforms = []
        for obj in bpy.context.scene.objects:
            if obj.type == 'MESH' and not in_wgts_collection(obj):
                loc_ok = all(abs(v) < 1e-4 for v in obj.location)
                rot_ok = all(abs(v) < 1e-4 for v in obj.rotation_euler)
                scale_ok = all(abs(v - 1.0) < 1e-4 for v in obj.scale)

                if not (loc_ok and rot_ok and scale_ok):
                    wrong_transforms.append(
                        f"{obj.name} "
                        f"(Loc: {tuple(round(v, 3) for v in obj.location)}, "
                        f"Rot: {tuple(round(v, 3) for v in obj.rotation_euler)}, "
                        f"Scale: {tuple(round(v, 3) for v in obj.scale)})"
                    )

        if wrong_transforms:
            results.append("[FAIL] Objects with unapplied transforms:\n" + "\n".join(wrong_transforms))
            all_ok = False
        else:
            results.append("[OK] All mesh objects have applied transforms")

        # --- Check that all modifiers are applied (except SubdivisionSurface)
        bad_mods = []
        for obj in bpy.context.scene.objects:
            if obj.type == 'MESH' and not in_wgts_collection(obj):
                for mod in obj.modifiers:
                    if mod.type != 'SUBSURF':  # разрешаем только Subdivision
                        bad_mods.append(f"{obj.name} → {mod.name} ({mod.type})")

        if bad_mods:
            results.append("[FAIL] Objects with unapplied modifiers:\n  " + "\n  ".join(bad_mods))
            all_ok = False
        else:
            results.append("[OK] No unapplied modifiers (except Subdivision)")

        # --- Check for n-gons
        ngon_objs = []
        for obj in bpy.context.scene.objects:
            if obj.type == 'MESH' and not in_wgts_collection(obj):
                mesh = obj.data
                for poly in mesh.polygons:
                    if poly.loop_total > 4:
                        ngon_objs.append(f"{obj.name} (poly {poly.index} has {poly.loop_total} sides)")
                        break

        if ngon_objs:
            results.append("[FAIL] Objects with n-gons:\n" + "\n".join(ngon_objs))
            all_ok = False
        else:
            results.append("[OK] No n-gons found in meshes")

        # --- Check for Shade Flat (no smooth)
        bad_flat = []
        for obj in bpy.context.scene.objects:
            if obj.type == 'MESH' and not in_wgts_collection(obj):
                mesh = obj.data
                if not any(poly.use_smooth for poly in mesh.polygons):
                    bad_flat.append(obj.name)

        if bad_flat:
            results.append("[FAIL] Objects without Shade Smooth:\n" + "\n".join(bad_flat))
            all_ok = False
        else:
            results.append("[OK] All objects have Shade Smooth")
            
        # --- Check for animation
        anim_objs = []
        for obj in bpy.context.scene.objects:
            if obj.type == 'MESH' and not in_wgts_collection(obj):
                if obj.animation_data and (obj.animation_data.action or obj.animation_data.drivers):
                    anim_objs.append(f"{obj.name} has animation data")

        if anim_objs:
            results.append("[FAIL] Objects with animation:\n" + "\n".join(anim_objs))
            all_ok = False
        else:
            results.append("[OK] No animation found in meshes")
            
        
        # --- Check for orphan data
        orphans = []

        # Проверяем основные типы данных
        for datablock_type, datablocks in {
            "Meshes": bpy.data.meshes,
            "Materials": bpy.data.materials,
            "Images": bpy.data.images,
            "Actions": bpy.data.actions,
            "Node Groups": bpy.data.node_groups,
            "Collections": bpy.data.collections,
        }.items():
            for datablock in datablocks:
                if datablock.users == 0:
                    orphans.append(f"{datablock_type}: {datablock.name}")

        if orphans:
            results.append("[FAIL] Orphan data blocks found:\n" + "\n".join(orphans))
            all_ok = False
        else:
            results.append("[OK] No orphan data found")
            
        # --- Check for default material names
        default_materials = []
        for mat in bpy.data.materials:
            if mat.users > 0:  # используемые материалы
                if mat.name.startswith("Material"):
                    default_materials.append(f"Material '{mat.name}' has default name")

        if default_materials:
            results.append("[FAIL] Materials with default names:\n" + "\n".join(default_materials))
            all_ok = False
        else:
            results.append("[OK] No materials with default names found")


        # --- Check for edges connected to more than 2 faces
        nonmanifold_objs = []
        for obj in bpy.context.scene.objects:
            if obj.type == 'MESH' and not in_wgts_collection(obj):
                mesh = obj.data
                bm = bmesh.new()
                bm.from_mesh(mesh)
                bm.normal_update()

                bad_edges = [e for e in bm.edges if len(e.link_faces) > 2]
                if bad_edges:
                    nonmanifold_objs.append(obj.name)

                bm.free()

        if nonmanifold_objs:
            results.append("[FAIL] Objects with non-manifold edges (connected to more than 2 faces):\n" + "\n".join(nonmanifold_objs))
            all_ok = False
        else:
            results.append("[OK] No non-manifold edges")
            
        # --- Check for isolated (loose) vertices
        isolated_verts_objs = []
        for obj in bpy.context.scene.objects:
            if obj.type == 'MESH' and not in_wgts_collection(obj):
                mesh = obj.data
                bm = bmesh.new()
                bm.from_mesh(mesh)
                bm.normal_update()

                loose_verts = [v for v in bm.verts if not v.link_edges and not v.link_faces]
                if loose_verts:
                    isolated_verts_objs.append(obj.name)

                bm.free()

        if isolated_verts_objs:
            results.append("[FAIL] Objects with isolated (loose) vertices:\n" + "\n".join(isolated_verts_objs))
            all_ok = False
        else:
            results.append("[OK] No isolated vertices")
            
        # --- Check for loose edges (edges without faces)
        loose_edges_objs = []
        for obj in bpy.context.scene.objects:
            if obj.type == 'MESH' and not in_wgts_collection(obj):
                mesh = obj.data
                bm = bmesh.new()
                bm.from_mesh(mesh)
                bm.normal_update()

                bad_edges = [e for e in bm.edges if len(e.link_faces) == 0]
                if bad_edges:
                    loose_edges_objs.append(obj.name)

                bm.free()

        if loose_edges_objs:
            results.append("[FAIL] Objects with loose edges (edges not connected to any face):\n" + "\n".join(loose_edges_objs))
            all_ok = False
        else:
            results.append("[OK] No loose edges")

        # --- Popup with full report
        message = "\n".join(results)

        def draw(self_popup, _context):
            for line in message.split("\n"):
                icon = 'CHECKMARK' if line.startswith("[OK]") else ('ERROR' if line.startswith("[FAIL]") else 'INFO')
                self_popup.layout.label(text=line, icon=icon)

        context.window_manager.popup_menu(draw, title="Modeling Check", icon='MESH_DATA')

        return {'FINISHED' if all_ok else 'CANCELLED'}

      

class OBJECT_OT_fix_pose_rotations(bpy.types.Operator):
    """Convert all pose bones to XYZ Euler"""
    bl_idname = "object.fix_pose_rotations"
    bl_label = "Convert Pose Rotations to XYZ Euler"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        rig_obj = context.object
        if not rig_obj or rig_obj.type != 'ARMATURE':
            self.report({'ERROR'}, "Active object is not an armature")
            return {'CANCELLED'}

        changed = []
        for pbone in rig_obj.pose.bones:
            if pbone.rotation_mode != 'XYZ':
                changed.append(f"{pbone.name} ({pbone.rotation_mode})")
                pbone.rotation_mode = 'XYZ'

        if changed:
            # Всплывающее сообщение с перечислением костей
            self.report({'INFO'}, f"Converted: {', '.join(changed)}")
        else:
            self.report({'INFO'}, "All pose bones already XYZ Euler")

        return {'FINISHED'}

def ensure_wgts_collection(asset_name: str):
    """Ensure WGTS collection exists inside _main"""
    main_coll = bpy.data.collections.get(f"{asset_name}_main")
    if not main_coll:
        main_coll = bpy.data.collections.new(f"{asset_name}_main")
        bpy.context.scene.collection.children.link(main_coll)

    wgts_coll = main_coll.children.get("WGTS")
    if not wgts_coll:
        wgts_coll = bpy.data.collections.new("WGTS")
        main_coll.children.link(wgts_coll)
    wgts_coll.hide_viewport = True
    wgts_coll.hide_render = True

    return wgts_coll


def create_circle_widget(name, collection, radius=1.0, scale=(1.0, 1.0, 1.0)):
    obj = bpy.data.objects.get(name)
    if obj and obj.type == 'MESH':
        if collection and obj.name not in collection.objects:
            try:
                collection.objects.link(obj)
            except Exception:
                pass
        obj.scale = scale
        obj.hide_select = True
        return obj

    mesh = bpy.data.meshes.new(f"{name}Shape")
    verts = []
    edges = []
    count = 32
    for index in range(count):
        angle = (math.tau * index) / count
        verts.append((math.sin(angle) * radius, -math.cos(angle) * radius, 0.0))
        edges.append((index, (index + 1) % count))
    mesh.from_pydata(verts, edges, [])
    mesh.update()

    obj = bpy.data.objects.new(name, mesh)
    obj.scale = scale
    obj.hide_select = True
    obj.hide_render = False
    if collection:
        collection.objects.link(obj)
    return obj


def ensure_basic_widgets(asset_name: str):
    wgts_coll = ensure_wgts_collection(asset_name)
    root_wgt = create_circle_widget("WGT-Root", wgts_coll, radius=1.0, scale=(1.0, 1.0, 1.0))
    main_wgt = create_circle_widget("WGT-Main", wgts_coll, radius=1.0, scale=(0.8, 0.8, 0.8))
    return root_wgt, main_wgt


def mesh_bounds_points(objects):
    points = []
    for obj in objects or []:
        if obj is None or obj.type != 'MESH':
            continue
        try:
            points.extend([obj.matrix_world @ Vector(corner) for corner in obj.bound_box])
        except Exception:
            continue
    return points


def mesh_bounds_metrics(objects):
    points = mesh_bounds_points(objects)
    if not points:
        return {
            "center": Vector((0.0, 0.0, 0.0)),
            "bottom": Vector((0.0, 0.0, 0.0)),
            "horizontal_radius": 1.0,
        }
    min_x = min(point.x for point in points)
    max_x = max(point.x for point in points)
    min_y = min(point.y for point in points)
    max_y = max(point.y for point in points)
    min_z = min(point.z for point in points)
    max_z = max(point.z for point in points)
    center = Vector(((min_x + max_x) * 0.5, (min_y + max_y) * 0.5, (min_z + max_z) * 0.5))
    bottom = Vector((center.x, center.y, min_z))
    horizontal_radius = max(max_x - min_x, max_y - min_y) * 0.5
    return {
        "center": center,
        "bottom": bottom,
        "horizontal_radius": max(horizontal_radius, 0.1),
    }


def collection_mesh_objects_recursive(collection, visited=None):
    if collection is None:
        return []
    if visited is None:
        visited = set()
    collection_key = collection.as_pointer()
    if collection_key in visited:
        return []
    visited.add(collection_key)
    if collection.name == "WGTS":
        return []

    meshes = []
    for obj in collection.objects:
        if obj.type != 'MESH':
            continue
        if obj.name.startswith("WGT-"):
            continue
        meshes.append(obj)

    for child in collection.children:
        meshes.extend(collection_mesh_objects_recursive(child, visited))
    return meshes


def get_asset_mesh_objects(coll_main, coll_geo):
    geo_meshes = collection_mesh_objects_recursive(coll_geo) if coll_geo else []
    if geo_meshes:
        return geo_meshes
    return collection_mesh_objects_recursive(coll_main)


def apply_root_main_widget_scale(rig_obj, root_widget, main_widget, object_radius):
    if rig_obj is None or rig_obj.type != 'ARMATURE':
        return
    try:
        rig_obj.data.show_bone_colors = True
    except Exception:
        pass
    # Keep a stable visual gap from the object instead of scaling the gap
    # proportionally with the asset size.
    root_radius = max(object_radius + 0.05, 0.05)
    main_radius = max(object_radius + 0.03, 0.03)
    pbone_root = rig_obj.pose.bones.get("Root")
    pbone_main = rig_obj.pose.bones.get("Main")
    if pbone_root:
        pbone_root.custom_shape = root_widget
        pbone_root.use_custom_shape_bone_size = False
        pbone_root.custom_shape_scale_xyz = (main_radius, main_radius, main_radius)
    if pbone_main:
        pbone_main.custom_shape = main_widget
        pbone_main.use_custom_shape_bone_size = False
        main_scale = root_radius * 0.8
        pbone_main.custom_shape_scale_xyz = (main_scale, main_scale, main_scale)
import bpy
from mathutils import Vector, Matrix
import os

class CreateSimpleRigOperator(bpy.types.Operator):
    """Simple rig generator"""
    bl_idname = "object.create_simple_rig"
    bl_label = "Create Simple Rig"
    bl_options = {'REGISTER', 'UNDO'}

    asset_name: bpy.props.StringProperty(name="Asset Name")

    # ----------------------------
    # INVOKE
    # ----------------------------
    def invoke(self, context, event):
        filename = bpy.path.basename(bpy.data.filepath)
        default_name = os.path.splitext(filename)[0] if filename else "AssetName"
        self.asset_name = default_name
        return context.window_manager.invoke_props_dialog(self)

    # ----------------------------
    # EXECUTE
    # ----------------------------
    def execute(self, context):

        # ----------------------------
        # 1. ONLY SELECTION
        # ----------------------------
        meshes = [o for o in context.selected_objects if o.type == 'MESH']

        if not meshes:
            self.report({'ERROR'}, "No mesh objects selected.")
            return {'CANCELLED'}

        # ----------------------------
        # 2. NAME
        # ----------------------------
        base_name = self.asset_name.strip() or meshes[0].name.split('.')[0]

        rig_name = f"{base_name}_rig"
        arm_name = f"{base_name}_armature"

        # ----------------------------
        # 3. CENTER (FROM SELECTION ONLY)
        # ----------------------------
        center = Vector((0.0, 0.0, 0.0))
        for obj in meshes:
            center += obj.matrix_world.translation
        center /= len(meshes)
        if center.z < 0:
            center.z = 0.0

        # ----------------------------
        # 4. BOUNDS
        # ----------------------------
        bounds_min = Vector((1e10, 1e10, 1e10))
        bounds_max = Vector((-1e10, -1e10, -1e10))

        for obj in meshes:
            for corner in obj.bound_box:
                world_corner = obj.matrix_world @ Vector(corner)

                bounds_min.x = min(bounds_min.x, world_corner.x)
                bounds_min.y = min(bounds_min.y, world_corner.y)
                bounds_min.z = min(bounds_min.z, world_corner.z)

                bounds_max.x = max(bounds_max.x, world_corner.x)
                bounds_max.y = max(bounds_max.y, world_corner.y)
                bounds_max.z = max(bounds_max.z, world_corner.z)

        size = bounds_max - bounds_min
        radius = max(size.x, size.y) * 0.5
        bottom_z = max(bounds_min.z, 0.0)

        bottom = Vector((
            center.x,
            center.y,
            bottom_z
        ))

        # ----------------------------
        # 5. CREATE ARMATURE (NO OPS)
        # ----------------------------
        arm_data = bpy.data.armatures.new(arm_name)
        rig_obj = bpy.data.objects.new(rig_name, arm_data)

        rig_obj.matrix_world = Matrix.Translation(center)
        rig_obj.scale = (1.0, 1.0, 1.0)
        rig_obj.rotation_euler = (0.0, 0.0, 0.0)
        rig_obj.hide_render = True

        # link
        coll_main = bpy.data.collections.get(f"{base_name}_main")
        if not coll_main:
            self.report({'ERROR'}, f"Collection {base_name}_main not found.")
            return {'CANCELLED'}

        coll_main.objects.link(rig_obj)

        # ----------------------------
        # 6. HARD CONTEXT RESET (IMPORTANT FOR STABILITY)
        # ----------------------------
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
        bpy.context.view_layer.update()

        rig_obj.select_set(True)
        bpy.context.view_layer.objects.active = rig_obj

        bpy.context.view_layer.update()

        # freeze matrix to avoid accumulation bugs
        rig_obj.matrix_world = Matrix.Translation(center)

        bpy.context.view_layer.update()

        # ----------------------------
        # 7. EDIT MODE SAFE ENTRY
        # ----------------------------
        bpy.ops.object.mode_set(mode='EDIT')

        eb = rig_obj.data.edit_bones

        # SAFE CLEAN (NO clear())
        for b in list(eb):
            eb.remove(b)

        inv = rig_obj.matrix_world.inverted()

        root_head_world = bottom
        main_head_world = bottom

        root_head = inv @ root_head_world
        main_head = inv @ main_head_world

        root_len = max(radius * 2.0, 0.2)

        root_tail = root_head + Vector((0.0, root_len, 0.0))
        main_tail = main_head + Vector((0.0, root_len, 0.0))

        # ----------------------------
        # 8. BONES
        # ----------------------------
        root = eb.new("Root")
        root.head = root_head
        root.tail = root_tail
        root.use_deform = False

        main = eb.new("Main")
        main.head = main_head
        main.tail = main_tail
        main.parent = root

        # ----------------------------
        # 9. BACK TO OBJECT MODE
        # ----------------------------
        bpy.ops.object.mode_set(mode='OBJECT')

        # ----------------------------
        # 10. POSE SETTINGS
        # ----------------------------
        p_root = rig_obj.pose.bones["Root"]
        p_main = rig_obj.pose.bones["Main"]

        p_root.rotation_mode = 'XYZ'
        p_main.rotation_mode = 'XYZ'

        p_root.color.palette = 'CUSTOM'
        p_root.color.custom.normal = (1, 0, 0)
        p_root.color.custom.select = (1.0, 0.0, 0.0)
        p_root.color.custom.active = (1.0, 0.0, 0.0)

        p_main.color.palette = 'CUSTOM'
        p_main.color.custom.normal = (1, 1, 0)
        p_main.color.custom.select = (1.0, 1.0, 0.0)
        p_main.color.custom.active = (1.0, 1.0, 0.0)

        # ----------------------------
        # 11. WIDGETS
        # ----------------------------
        root_wgt, main_wgt = ensure_basic_widgets(base_name)
        apply_root_main_widget_scale(
            rig_obj,
            root_wgt,
            main_wgt,
            radius
        )

        # ----------------------------
        # 12. AUTO PARENT
        # ----------------------------
        bpy.ops.object.select_all(action='DESELECT')

        for obj in meshes:
            obj.select_set(True)

        rig_obj.select_set(True)
        bpy.context.view_layer.objects.active = rig_obj

        bpy.ops.object.parent_set(type='ARMATURE_AUTO')

        self.report({'INFO'}, f"Simple rig created: {rig_name}")
        return {'FINISHED'}

class POSE_OT_add_visibility_property(bpy.types.Operator):
    """Add integer visibility property to a pose bone and apply object visibility drivers"""
    bl_idname = "pose.add_visibility_property"
    bl_label = "Add Visibility"
    bl_options = {'REGISTER', 'UNDO'}

    @staticmethod
    def ensure_visibility_property(bone):
        if bone is None:
            return
        current = bone.get("Visibility", 1)
        try:
            current = int(round(float(current)))
        except Exception:
            current = 1
        bone["Visibility"] = max(0, min(1, current))
        try:
            ui_data = bone.id_properties_ui("Visibility")
            ui_data.update(
                min=0,
                max=1,
                soft_min=0,
                soft_max=1,
                default=1,
                description="1 = visible, 0 = hidden",
            )
        except Exception:
            pass
        try:
            bone.property_overridable_library_set('["Visibility"]', True)
        except Exception:
            pass

    @staticmethod
    def apply_visibility_driver_to_target(target_obj, armature_obj, bone):
        if target_obj is None or armature_obj is None or bone is None:
            return
        if hasattr(bone, "path_from_id"):
            data_path = bone.path_from_id() + '["Visibility"]'
        else:
            data_path = f'pose.bones["{bone.name}"]["Visibility"]'
        for prop_name in ("hide_viewport", "hide_render"):
            try:
                target_obj.driver_remove(prop_name)
            except Exception:
                pass
            driver = target_obj.driver_add(prop_name).driver
            driver.type = 'SCRIPTED'
            variable = driver.variables.new()
            variable.name = "vis"
            variable.type = 'SINGLE_PROP'
            target = variable.targets[0]
            target.id_type = 'OBJECT'
            target.id = armature_obj
            target.data_path = data_path
            driver.expression = "1 - vis"
        try:
            armature_obj.update_tag()
        except Exception:
            pass
        try:
            target_obj.update_tag()
        except Exception:
            pass
        try:
            bpy.context.view_layer.update()
        except Exception:
            pass
        try:
            current_frame = bpy.context.scene.frame_current
            bpy.context.scene.frame_set(current_frame)
        except Exception:
            pass

    def execute(self, context):
        scene = context.scene
        target_obj = getattr(scene, "ac_target_object", None)
        armature_obj = getattr(scene, "ac_armature_object", None)
        bone_name = str(getattr(scene, "ac_bone_name", "") or "").strip()

        bone = None
        if armature_obj and armature_obj.type == 'ARMATURE' and bone_name in armature_obj.pose.bones:
            bone = armature_obj.pose.bones[bone_name]
        elif context.active_pose_bone is not None and context.active_object and context.active_object.type == 'ARMATURE':
            armature_obj = context.active_object
            bone = context.active_pose_bone
            scene.ac_armature_object = armature_obj
            scene.ac_bone_name = bone.name

        if bone is None or armature_obj is None:
            self.report({'WARNING'}, "Выбери Armature и Bone или активную кость в Pose Mode")
            return {'CANCELLED'}

        self.ensure_visibility_property(bone)

        if target_obj is None:
            self.report({'INFO'}, f"Visibility 0/1 создан на {bone.name}. Выбери Target для драйвера.")
            return {'FINISHED'}

        self.apply_visibility_driver_to_target(target_obj, armature_obj, bone)
        self.report({'INFO'}, f"Visibility 0/1 + driver: {bone.name} -> {target_obj.name}")
        return {'FINISHED'}


class POSE_OT_use_active_bone_for_visibility(bpy.types.Operator):
    """Use the currently active pose bone as the visibility driver source"""
    bl_idname = "pose.use_active_bone_for_visibility"
    bl_label = "Use Active Bone"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        active_obj = context.active_object
        active_bone = context.active_pose_bone
        if active_obj is None or active_obj.type != 'ARMATURE' or active_bone is None:
            self.report({'WARNING'}, "Select an armature in Pose Mode and make a bone active")
            return {'CANCELLED'}
        context.scene.ac_armature_object = active_obj
        context.scene.ac_bone_name = active_bone.name
        self.report({'INFO'}, f"Selected active bone: {active_bone.name}")
        return {'FINISHED'}


class AlignBonesToYOperator(bpy.types.Operator):
    """Align Root and Main bones along +Y axis, keeping head in place"""
    bl_idname = "armature.align_bones_y"
    bl_label = "Align Root/Main to +Y"

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'ARMATURE':
            self.report({'ERROR'}, "Active object must be an armature")
            return {'CANCELLED'}

        arm = obj.data
        bpy.ops.object.mode_set(mode='EDIT')

        # --- Переставляем кости в +Y
        for bone_name in ["Root", "Main"]:
            if bone_name in arm.edit_bones:
                bone = arm.edit_bones[bone_name]
                length = bone.length
                hx, hy, hz = bone.head
                bone.tail = (hx, hy + length, hz)  # вдоль +Y
            else:
                self.report({'WARNING'}, f"Bone {bone_name} not found")

        bpy.ops.object.mode_set(mode='POSE')

        # --- Выбираем кости и создаём виджеты
        for bone_name in ["Main", "Root"]:
            if bone_name in obj.data.bones:
                obj.data.bones[bone_name].select = True
        if "Main" in obj.pose.bones:
            obj.data.bones.active = obj.pose.bones["Main"].bone

        bpy.context.scene.widget_list = 'Circle'
        bpy.ops.bonewidget.create_widget(rotation=(1.5708, 0, 0))

        bpy.ops.object.mode_set(mode='OBJECT')
        self.report({'INFO'}, "Bones aligned to +Y (head kept in place)")
        return {'FINISHED'}




def get_selected_vertex_world(obj):
    """Returns a list of (coordinate, normal) for selected vertices"""
    if obj is None or obj.type != 'MESH':
        return []

    coords_normals = []
    mat = obj.matrix_world
    mat_norm = mat.to_3x3().inverted().transposed()

    if obj.mode == 'EDIT':
        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        for v in bm.verts:
            if v.select:
                coords_normals.append((
                    mat @ v.co,
                    (mat_norm @ v.normal).normalized()
                ))
    else:
        for v in obj.data.vertices:
            if v.select:
                coords_normals.append((
                    mat @ v.co,
                    (mat_norm @ v.normal).normalized()
                ))

    return coords_normals


def get_or_create_armature(context):
    """Finds the first armature, or creates a new one if none exists"""
    for obj in context.scene.objects:
        if obj.type == 'ARMATURE':
            return obj

    arm_data = bpy.data.armatures.new("BonesFromSelectionArm")
    arm_obj = bpy.data.objects.new("BonesFromSelection", arm_data)

    # Add to the root scene collection (Scene Collection)
    context.scene.collection.objects.link(arm_obj)

    return arm_obj


class OBJECT_OT_bones_from_selection(bpy.types.Operator):
    """Create a bone at each selected vertex"""
    bl_idname = "object.bones_from_selection"
    bl_label = "Create Bones from Selection"
    bl_options = {'REGISTER', 'UNDO'}

    bone_length: FloatProperty(
        name="Bone Length",
        description="Length of created bones (in Blender units)",
        default=1.0,
        min=0.001,
        max=100.0
    )

    use_normal: BoolProperty(
        name="Align to Normal",
        description="If enabled, bones will be created along vertex normals instead of Z axis",
        default=False
    )

    def execute(self, context):
        obj = context.active_object

        if obj is None or obj.type != 'MESH':
            self.report({'ERROR'}, "Need a mesh object with selected vertices.")
            return {'CANCELLED'}

        coords_normals = get_selected_vertex_world(obj)
        if not coords_normals:
            self.report({'ERROR'}, "No selected vertices.")
            return {'CANCELLED'}

        # Remember previous mode
        prev_mode = obj.mode

        # Get or create armature
        arm_obj = get_or_create_armature(context)
        arm = arm_obj.data

        # Switch to armature edit mode
        bpy.ops.object.mode_set(mode='OBJECT')
        context.view_layer.objects.active = arm_obj
        arm_obj.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT')

        for idx, (world_co, world_no) in enumerate(coords_normals):
            bone_name = f"vtx_{idx+1}"
            eb = arm.edit_bones.new(bone_name)
            local_head = arm_obj.matrix_world.inverted() @ world_co
            eb.head = local_head

            if self.use_normal:
                direction = (arm_obj.matrix_world.inverted().to_3x3() @ world_no).normalized()
            else:
                direction = Vector((0.0, 0.0, 1.0))

            eb.tail = local_head + direction * self.bone_length
            eb.use_connect = False

        # Restore previous mode
        bpy.ops.object.mode_set(mode='OBJECT')
        context.view_layer.objects.active = obj
        obj.select_set(True)
        if prev_mode == 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')

        self.report({'INFO'}, f"Created {len(coords_normals)} bones in '{arm_obj.name}'")
        return {'FINISHED'}



import bpy
from mathutils import Vector
from bpy.props import FloatProperty, BoolProperty


class OBJECT_OT_bone_center_from_selection(bpy.types.Operator):
    """Create bones at centers of selected objects"""
    bl_idname = "object.bone_center_from_selection"
    bl_label = "Create Bones at Centers"
    bl_options = {'REGISTER', 'UNDO'}

    bone_length: FloatProperty(
        name="Bone Length",
        default=1.0,
        min=0.001,
        max=100.0
    )

    use_normal: BoolProperty(
        name="Align to Average Normal",
        default=False
    )

    # ----------------------------------------------------
    # FIND RIG
    # ----------------------------------------------------
    def find_rig_armature(self, context):

        # find *_main collection
        main_col = None
        for col in bpy.data.collections:
            if col.name.endswith("_main"):
                main_col = col
                break

        if not main_col:
            return None, "Collection '*_main' not found"

        # find *_rig armature object inside *_main
        arm_obj = None
        for obj in main_col.all_objects:
            if obj.type == 'ARMATURE' and obj.name.endswith("_rig"):
                arm_obj = obj
                break

        if not arm_obj:
            return None, "No armature ending with '_rig' found inside '*_main'"

        return arm_obj, None

    # ----------------------------------------------------
    # EXECUTE
    # ----------------------------------------------------
    def execute(self, context):

        selected_objects = [
            obj for obj in context.selected_objects if obj.type == 'MESH'
        ]

        if not selected_objects:
            self.report({'ERROR'}, "No mesh objects selected.")
            return {'CANCELLED'}

        # --- find rig ---
        arm_obj, error = self.find_rig_armature(context)
        if error:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}

        arm = arm_obj.data

        # --- check Main bone ---
        if "Main" not in arm.bones:
            self.report({'ERROR'}, "Bone 'Main' not found in armature.")
            return {'CANCELLED'}

        prev_active = context.view_layer.objects.active

        # --- switch to edit mode ---
        bpy.ops.object.mode_set(mode='OBJECT')
        context.view_layer.objects.active = arm_obj
        arm_obj.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT')

        main_bone = arm.edit_bones["Main"]

        created_bones = {}

        # ----------------------------------------------------
        # CREATE BONES PER OBJECT
        # ----------------------------------------------------
        for obj in selected_objects:

            coords_normals = get_selected_vertex_world(obj)

            if coords_normals:
                avg_co = sum((co for co, no in coords_normals), Vector()) / len(coords_normals)
                avg_no = sum((no for co, no in coords_normals), Vector())
                if avg_no.length:
                    avg_no.normalize()
            else:
                avg_co = obj.matrix_world.translation
                avg_no = Vector((0, 0, 1))

            bone_name = f"bone_{obj.name}"

            eb = arm.edit_bones.new(bone_name)

            local_head = arm_obj.matrix_world.inverted() @ avg_co
            eb.head = local_head

            if self.use_normal:
                direction = (arm_obj.matrix_world.inverted().to_3x3() @ avg_no).normalized()
            else:
                direction = Vector((0.0, 0.0, 1.0))

            eb.tail = local_head + direction * self.bone_length

            eb.parent = main_bone
            eb.use_connect = False

            created_bones[obj.name] = bone_name

        # --- back to object mode ---
        bpy.ops.object.mode_set(mode='OBJECT')

        # ----------------------------------------------------
        # PARENT OBJECTS TO BONES
        # ----------------------------------------------------
        for obj in selected_objects:

            bone_name = created_bones[obj.name]

            # активируем armature
            context.view_layer.objects.active = arm_obj

            # сохраняем world matrix
            mw = obj.matrix_world.copy()

                # parenting
            obj.parent = arm_obj
            obj.parent_type = 'BONE'
            obj.parent_bone = bone_name

            # 🔥 CRITICAL FIX: restore world position correctly
            obj.matrix_world = mw
        context.view_layer.objects.active = prev_active

        self.report({'INFO'}, f"Created {len(created_bones)} bones in {arm_obj.name}")
        return {'FINISHED'}

class ResetRigPoseOperator(bpy.types.Operator):
    bl_idname = "object.reset_rig_pose"
    bl_label = "Reset Rig Pose"
    bl_description = "Go to Pose Mode, reset all bones, and return back"

    def execute(self, context):
        obj = context.object
        if not obj or obj.type != 'ARMATURE':
            self.report({'WARNING'}, "Select an armature")
            return {'CANCELLED'}

        # Запоминаем текущий режим
        prev_mode = obj.mode

        # Переход в Pose Mode (если не там)
        if prev_mode != 'POSE':
            bpy.ops.object.mode_set(mode='POSE')

        # Выделяем все кости
        bpy.ops.pose.select_all(action='SELECT')

        # Сбрасываем трансформации
        bpy.ops.pose.transforms_clear()

        # Возвращаемся в исходный режим
        if prev_mode != 'POSE':
            bpy.ops.object.mode_set(mode=prev_mode)

        return {'FINISHED'}


class MoveSubdivToBottomOperator(bpy.types.Operator):
    bl_idname = "object.move_subdiv_to_bottom"
    bl_label = "Move Subdiv Modifiers to Bottom"
    bl_description = "Move all Subdivision Surface modifiers to the bottom for all meshes"

    def execute(self, context):
        moved_objects = []

        # Сохраняем активный объект
        prev_active = context.view_layer.objects.active

        for obj in bpy.context.scene.objects:
            if obj.type != 'MESH':
                continue

            mods = obj.modifiers
            subdiv_mods = [m for m in mods if m.type == 'SUBSURF']
            if not subdiv_mods:
                continue

            moved = False
            # Делаем объект активным, чтобы bpy.ops сработал
            context.view_layer.objects.active = obj

            for mod in subdiv_mods:
                while mods[-1] != mod:
                    bpy.ops.object.modifier_move_down(modifier=mod.name)
                    moved = True

            if moved:
                moved_objects.append(obj.name)

        # Восстанавливаем активный объект
        context.view_layer.objects.active = prev_active

        if moved_objects:
            self.report({'INFO'}, f"Moved Subdivision modifiers to bottom in: {', '.join(moved_objects)}")
        else:
            self.report({'INFO'}, "All Subdivision modifiers are already at the bottom")

        return {'FINISHED'}
        
# Оператор для исключения/включения коллекции WGTS
class ToggleWGTSExcludeOperator(bpy.types.Operator):
    """Переключить видимость коллекции WGTS во всех режимах"""
    bl_idname = "object.toggle_wgts_exclude"
    bl_label = "Toggle WGTS Visibility"
    bl_options = {'REGISTER', 'UNDO'}
    
    # Рекурсивная функция для поиска layer_collection
    def find_layer_collection(self, layer_coll, coll_name):
        if layer_coll.name == coll_name:
            return layer_coll
        for child in layer_coll.children:
            found = self.find_layer_collection(child, coll_name)
            if found:
                return found
        return None
    
    def execute(self, context):
        wgts_name = "WGTS"
        
        # Ищем layer_collection и саму коллекцию
        layer_coll = self.find_layer_collection(context.view_layer.layer_collection, wgts_name)
        wgts_coll = bpy.data.collections.get(wgts_name)
        
        if not wgts_coll:
            self.report({'WARNING'}, f"Коллекция {wgts_name} не найдена")
            return {'CANCELLED'}
        
        # Пробуем получить текущее состояние через hide_get()
        try:
            # Пробуем разные варианты использования hide_get()
            current_state = wgts_coll.hide_get(view_layer=context.view_layer)
        except:
            try:
                current_state = wgts_coll.hide_get()
            except:
                # Если hide_get() не работает, используем hide_viewport как fallback
                current_state = wgts_coll.hide_viewport
        
        # Определяем новое состояние
        new_state = not current_state
        
        # Пробуем использовать hide_set() если доступно
        try:
            wgts_coll.hide_set(new_state, view_layer=context.view_layer)
            method_used = "hide_set(view_layer)"
        except:
            try:
                wgts_coll.hide_set(new_state)
                method_used = "hide_set()"
            except:
                # Fallback на прямое присвоение свойств
                wgts_coll.hide_viewport = new_state
                wgts_coll.hide_render = new_state
                method_used = "direct properties"
                
                # Пробуем установить hide_in_viewport если существует
                if hasattr(wgts_coll, 'hide_in_viewport'):
                    wgts_coll.hide_in_viewport = new_state
        
        # Управляем исключением из коллекции
        if layer_coll:
            layer_coll.exclude = new_state
        
        status = "скрыта" if new_state else "видима"
        self.report({'INFO'}, f"Коллекция {wgts_name} {status} ({method_used})")
        
        return {'FINISHED'}
        
class OBJECT_OT_reset_all_subdiv_levels(bpy.types.Operator):
    bl_idname = "object.reset_all_subdiv_levels"
    bl_label = "Reset All Subdivision Levels (Viewport)"
    bl_description = "Set viewport levels of all Subdivision modifiers in the scene to 0 and enable viewport visibility"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return len(bpy.data.objects) > 0

    def execute(self, context):
        subdiv_mods = [
            mod
            for obj in bpy.data.objects
            for mod in obj.modifiers
            if mod.type == 'SUBSURF'
        ]

        if not subdiv_mods:
            self.report({'INFO'}, "No Subdivision modifiers found")
            return {'CANCELLED'}

        for mod in subdiv_mods:
            mod.levels = 0  # viewport
            mod.show_viewport = True
            mod.show_in_editmode = True
            mod.show_on_cage = True

        self.report({'INFO'}, f"Reset {len(subdiv_mods)} Subdivision modifiers to viewport level 0")
        return {'FINISHED'}

class OBJECT_OT_toggle_subdiv_levels(bpy.types.Operator):
    bl_idname = "object.toggle_subdiv_levels"
    bl_label = "Toggle Subdivision Levels (0/1)"
    bl_description = "Toggle all Subdivision modifiers viewport levels between 0 and 1"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return len(bpy.data.objects) > 0

    def execute(self, context):
        subdiv_mods = [
            mod
            for obj in bpy.data.objects
            for mod in obj.modifiers
            if mod.type == 'SUBSURF'
        ]

        if not subdiv_mods:
            self.report({'INFO'}, "No Subdivision modifiers found")
            return {'CANCELLED'}

        # Проверяем текущее состояние
        any_nonzero = any(mod.levels != 0 for mod in subdiv_mods)

        new_level = 0 if any_nonzero else 1

        for mod in subdiv_mods:
            mod.levels = new_level
            mod.show_viewport = True
            mod.show_in_editmode = True
            mod.show_on_cage = True

        self.report({'INFO'}, f"Set {len(subdiv_mods)} Subdivision modifiers to viewport level {new_level}")
        return {'FINISHED'}
      
class OBJECT_OT_reset_3d_cursor(bpy.types.Operator):
    """Reset 3D Cursor to world origin with zero rotation"""
    bl_idname = "view3d.reset_3d_cursor"
    bl_label = "Reset 3D Cursor"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        cursor = context.scene.cursor
        cursor.location = (0.0, 0.0, 0.0)
        cursor.rotation_euler = (0.0, 0.0, 0.0)
        self.report({'INFO'}, "3D Cursor reset to (0,0,0) with zero rotation")
        return {'FINISHED'}



class AlignSelectedBoneToYOperator(bpy.types.Operator):
    """Align selected bones along +Y axis, keeping head in place, detach & reattach widgets"""
    bl_idname = "armature.align_selected_bone_y"
    bl_label = "Align Selected Bones to +Y"

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'ARMATURE':
            self.report({'ERROR'}, "Active object must be an armature")
            return {'CANCELLED'}

        if context.mode != 'POSE':
            self.report({'ERROR'}, "Must be in Pose Mode with bones selected")
            return {'CANCELLED'}

        selected = context.selected_pose_bones
        if not selected:
            self.report({'ERROR'}, "No bones selected")
            return {'CANCELLED'}

        # --- переходим в EDIT для всех костей сразу
        bpy.ops.object.mode_set(mode='EDIT')

        for pbone in selected:
            bone_name = pbone.name
            ebone = obj.data.edit_bones[bone_name]

            # --- запоминаем виджет
            widget = pbone.custom_shape

            # --- отцепляем
            pbone.custom_shape = None

            # --- двигаем хвост кости в +Y
            length = ebone.length
            hx, hy, hz = ebone.head
            ebone.tail = (hx, hy + length, hz)
            
            # --- сбрасываем ролл
            ebone.roll = 0.0

            # --- вернемся в POSE, прицепим обратно и повернем виджет
            bpy.ops.object.mode_set(mode='POSE')
            if widget:
                pbone = obj.pose.bones[bone_name]
                pbone.custom_shape = widget
                pbone.custom_shape_rotation_euler[0] = 1.5708  # X = 90°

            # --- обратно в EDIT для следующей кости
            bpy.ops.object.mode_set(mode='EDIT')

        # закончили, возвращаемся в POSE
        bpy.ops.object.mode_set(mode='POSE')

        self.report({'INFO'}, f"{len(selected)} bone(s) aligned to +Y and widgets reattached")
        return {'FINISHED'}


class OBJECT_OT_toggle_selectable(bpy.types.Operator):
    bl_idname = "object.toggle_selectable"
    bl_label = "Toggle Mesh Selectable"
    bl_description = "Toggle selectable state for all mesh objects (including *_geo collections)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return any(obj.type == 'MESH' for obj in bpy.data.objects)

    def execute(self, context):
        mesh_objects = [obj for obj in bpy.data.objects if obj.type == 'MESH']

        # --- Добавляем объекты и коллекции *_geo ---
        geo_collections = [col for col in bpy.data.collections if col.name.lower().endswith("_geo")]

        for col in geo_collections:
            for obj in col.all_objects:
                if obj.type == 'MESH' and obj not in mesh_objects:
                    mesh_objects.append(obj)

        if not mesh_objects and not geo_collections:
            self.report({'INFO'}, "No mesh objects or *_geo collections found")
            return {'CANCELLED'}

        # Проверяем текущее состояние (есть ли хоть один доступный для выбора объект или коллекция)
        any_selectable_obj = any(not obj.hide_select for obj in mesh_objects)
        any_selectable_col = any(not col.hide_select for col in geo_collections)
        any_selectable = any_selectable_obj or any_selectable_col

        # Если есть хоть что-то доступное — выключаем выбор, иначе включаем
        new_state = True if any_selectable else False

        # Применяем новое состояние к объектам
        for obj in mesh_objects:
            obj.hide_select = new_state

        # Применяем то же состояние к коллекциям *_geo
        for col in geo_collections:
            col.hide_select = new_state

        state_str = "disabled" if new_state else "enabled"
        self.report({'INFO'}, f"Selection {state_str} for {len(mesh_objects)} mesh objects and {len(geo_collections)} *_geo collections")
        return {'FINISHED'}
        
class REMOVE_BONE_CUSTOM_PROP_OT_operator(bpy.types.Operator):
    """Removes a custom property from all bones of the active armature"""
    bl_idname = "armature.remove_bone_custom_property"
    bl_label = "Remove Property"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        prop_name = context.scene.remove_bone_prop_name.strip()

        if not prop_name:
            self.report({'WARNING'}, "Enter a property name")
            return {'CANCELLED'}

        obj = context.object
        if not obj or obj.type != 'ARMATURE':
            self.report({'WARNING'}, "Active object must be an armature")
            return {'CANCELLED'}

        count = 0
        # Remove from bone data (data block)
        for bone in obj.data.bones:
            if prop_name in bone.keys():
                del bone[prop_name]
                count += 1

        # Remove from pose bones (runtime data, where custom properties are often stored)
        for pbone in obj.pose.bones:
            if prop_name in pbone.keys():
                del pbone[prop_name]
                count += 1

        self.report({'INFO'}, f"Removed properties: {count}")
        return {'FINISHED'}


class AssetPanel(bpy.types.Panel):
    bl_label = "Asset Tools"
    bl_idname = "VIEW3D_PT_asset_tools"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Assets'

    def draw(self, context):
        layout = self.layout
        
        # --- Overlay ---
        box = layout.box()
        box.label(text="Overlay", icon="INFO")
        overlay = context.space_data.overlay
        row = box.row(align=True)
        # Wireframe toggle
        row.prop(overlay, "show_wireframes", text="Wireframe", toggle=True)
        # Face Orientation toggle
        row.prop(overlay, "show_face_orientation", text="Face Orientation", toggle=True)

        # --- Modeling ---
        box = layout.box()
        box.label(text="Modeling", icon="MESH_CUBE")
        
        # Основные действия
        row = box.row(align=True)
        row.operator(SimpleAssetNameInput.bl_idname, text="Create Asset Collections", icon="OUTLINER_COLLECTION")
        row = box.row(align=True)
        row.operator(ApplyAllTransformsOperator.bl_idname, text="ApplyTransforms")
        row.operator(ShadeSmoothAllOperator.bl_idname, text="Smooth Shade")
        row = box.row(align=True)
        row.operator(OBJECT_OT_toggle_subdiv_levels.bl_idname, text="Toggle SubD Levels (0/1)")
        
        # Дополнительные действия
        row = box.row()
        row.operator(ModelingCheckOperator.bl_idname, text="Model Check", icon="CHECKMARK")

        # --- Scene cleanup ---
        box = layout.box()
        box.label(text="Scene Cleanup and Check", icon="TRASH")
        
        row = box.row(align=True)
        row.operator(ClearAnimationOperator.bl_idname, text="Animation", icon="TRASH")
        row.operator(PurgeOrphansOperator.bl_idname, text="Orphans", icon="TRASH")
        row = box.row(align=True)
        row.operator(OBJECT_OT_reset_3d_cursor.bl_idname, text="3D Cursor Reset", icon="PIVOT_CURSOR")
        row = box.row(align=True)
        row.operator(SceneCheckOperator.bl_idname, text="Scene Check", icon="CHECKMARK")

        # --- Shading ---
        box = layout.box()
        box.label(text="Shading", icon="MATERIAL")
        
        row = box.row(align=True)
        row.operator(RenameAllMaterialsOperator.bl_idname, text="Materials", icon="MATERIAL")
        row.operator(ReplaceTexturePathsOperator.bl_idname, text="Textures", icon="FILE_IMAGE")

        # --- Rig ---
        box = layout.box()
        box.label(text="Rig", icon="ARMATURE_DATA")
        
        # Основные инструменты риггинга
        row = box.row(align=True)
        row.operator("object.fix_pose_rotations", text="to XYZ Euler", icon="ARMATURE_DATA")
        row.operator(CreateSimpleRigOperator.bl_idname, text="Create Rig", icon="ARMATURE_DATA")
        row = box.row(align=True)
        row.operator("pose.add_visibility_property", text="Add Visibility", icon="PLUS")
        row = box.row(align=True)
        row.prop_search(context.scene, "ac_target_object", context.scene, "objects", text="Target")
        row = box.row(align=True)
        row.prop_search(context.scene, "ac_armature_object", context.scene, "objects", text="Armature")
        row = box.row(align=True)
        armature_obj = context.scene.ac_armature_object
        if armature_obj and armature_obj.type == 'ARMATURE':
            row.prop_search(context.scene, "ac_bone_name", armature_obj.data, "bones", text="Bone")
        else:
            row.prop(context.scene, "ac_bone_name", text="Bone")
        row.operator("pose.use_active_bone_for_visibility", text="", icon="EYEDROPPER")
        # Новая кнопка ресета позы
        row = box.row(align=True)
        row.operator("object.reset_rig_pose", text="Reset Rig Pose", icon="ARMATURE_DATA")
        # Кнопка для исключения WGTS
        row.operator("object.toggle_wgts_exclude", text="WGTS Exclude", icon="HIDE_ON")
        row = box.row(align=True)
        row.operator("object.move_subdiv_to_bottom", text="Fix Subdiv Order", icon="MOD_SUBSURF")
        row = box.row(align=True)
        #row.operator(AlignBonesToYOperator.bl_idname, text="Fix Bone Axis", icon="ARMATURE_DATA")
        row.operator(AlignSelectedBoneToYOperator.bl_idname, text="Fix Select Bones Axis", icon="ARMATURE_DATA")
        row = box.row(align=True)
        row.operator(OBJECT_OT_toggle_selectable.bl_idname, text="Selectable", icon="RESTRICT_SELECT_OFF")
                 
        #Create Bones from Verts
        sub_box = box.box()
        row = sub_box.row(align=True)
        
        row.prop(context.scene, "bones_from_selection_use_normal", text="Align to Normal")
        row.prop(context.scene, "bones_from_selection_length", text="Length")
        
        row = sub_box.row(align=True)
        op = row.operator(OBJECT_OT_bones_from_selection.bl_idname, text="Create Bones from Verts", icon="BONE_DATA")
        op.bone_length = context.scene.bones_from_selection_length
        op.use_normal = context.scene.bones_from_selection_use_normal
        
        row = sub_box.row(align=True)
        opm = row.operator(OBJECT_OT_bone_center_from_selection.bl_idname, text="Create Bone at the midpoint", icon="BONE_DATA")
        opm.bone_length = context.scene.bones_from_selection_length
        opm.use_normal = context.scene.bones_from_selection_use_normal
        
        # --- Remove Bone Property ---
        remove_box = box.box()
        remove_box.label(text="Remove Property from Bones", icon="X")
        remove_box.prop(context.scene, "remove_bone_prop_name", text="Name")
        remove_box.operator("armature.remove_bone_custom_property", text="Remove")
        
        # Проверка рига
        row = box.row()
        row.operator(RigCheckOperator.bl_idname, text="Rig Validation", icon="CHECKMARK")        
        
        
def register():
    bpy.utils.register_class(SimpleAssetNameInput)
    bpy.utils.register_class(CreateRigOperator)   # <-- добавлено
    bpy.utils.register_class(ApplyAllTransformsOperator)
    bpy.utils.register_class(RenameAllMaterialsOperator)
    bpy.utils.register_class(AssetPanel)
    bpy.utils.register_class(MoveTexturesOperator)
    bpy.utils.register_class(ClearAnimationOperator)
    bpy.utils.register_class(PurgeOrphansOperator)
    bpy.utils.register_class(OBJECT_OT_rename_asset_armature)
    bpy.utils.register_class(RigCheckOperator)
    bpy.utils.register_class(CreateSimpleRigOperator)
    bpy.utils.register_class(POSE_OT_add_visibility_property)
    bpy.utils.register_class(POSE_OT_use_active_bone_for_visibility)
    bpy.utils.register_class(OBJECT_OT_fix_pose_rotations)
    bpy.utils.register_class(ModelingCheckOperator)
    bpy.utils.register_class(ShadeSmoothAllOperator)
    bpy.utils.register_class(OBJECT_OT_bones_from_selection)
    bpy.utils.register_class(ResetRigPoseOperator)
    bpy.utils.register_class(ToggleWGTSExcludeOperator)
    bpy.utils.register_class(OBJECT_OT_toggle_subdiv_levels)
    bpy.utils.register_class(SceneCheckOperator)
    bpy.utils.register_class(OBJECT_OT_reset_3d_cursor)
    bpy.utils.register_class(AlignBonesToYOperator)
    bpy.utils.register_class(AlignSelectedBoneToYOperator)
    bpy.utils.register_class(OBJECT_OT_bone_center_from_selection)
    bpy.utils.register_class(MoveSubdivToBottomOperator)
    bpy.utils.register_class(OBJECT_OT_toggle_selectable)
    bpy.utils.register_class(ReplaceTexturePathsOperator)
    
    bpy.types.Scene.bones_from_selection_length = FloatProperty(
        name="Bone Length",
        default=1.0,
        min=0.001,
        max=100.0,
        description="Length of created bones"
    )
    bpy.types.Scene.bones_from_selection_use_normal = BoolProperty(
        name="Align to Normal",
        default=False,
        description="Create bones aligned to vertex normals"
    )
    bpy.types.Scene.ac_target_object = bpy.props.PointerProperty(type=bpy.types.Object)
    bpy.types.Scene.ac_armature_object = bpy.props.PointerProperty(type=bpy.types.Object)
    bpy.types.Scene.ac_bone_name = bpy.props.StringProperty(name="Bone Name", default="")
    
    bpy.utils.register_class(REMOVE_BONE_CUSTOM_PROP_OT_operator)
    bpy.types.Scene.remove_bone_prop_name = bpy.props.StringProperty(
        name="Property Name",
        description="Name of the custom property to remove",
        default=""
    )
    


def unregister():
    bpy.utils.unregister_class(AssetPanel)
    bpy.utils.unregister_class(RenameAllMaterialsOperator)
    bpy.utils.unregister_class(ApplyAllTransformsOperator)
    bpy.utils.unregister_class(CreateRigOperator)   # <-- добавлено
    bpy.utils.unregister_class(SimpleAssetNameInput)
    bpy.utils.unregister_class(MoveTexturesOperator)
    bpy.utils.unregister_class(PurgeOrphansOperator)
    bpy.utils.unregister_class(ClearAnimationOperator)
    bpy.utils.unregister_class(OBJECT_OT_rename_asset_armature)
    bpy.utils.unregister_class(RigCheckOperator)
    bpy.utils.unregister_class(CreateSimpleRigOperator)
    bpy.utils.unregister_class(POSE_OT_add_visibility_property)
    bpy.utils.unregister_class(POSE_OT_use_active_bone_for_visibility)
    bpy.utils.unregister_class(OBJECT_OT_fix_pose_rotations)
    bpy.utils.unregister_class(ModelingCheckOperator)
    bpy.utils.unregister_class(ShadeSmoothAllOperator)
    bpy.utils.unregister_class(OBJECT_OT_bones_from_selection)
    bpy.utils.unregister_class(ResetRigPoseOperator)
    bpy.utils.unregister_class(ToggleWGTSExcludeOperator)
    bpy.utils.unregister_class(OBJECT_OT_toggle_subdiv_levels)
    bpy.utils.unregister_class(SceneCheckOperator)
    bpy.utils.unregister_class(OBJECT_OT_reset_3d_cursor)
    bpy.utils.unregister_class(AlignBonesToYOperator)
    bpy.utils.unregister_class(AlignSelectedBoneToYOperator)
    bpy.utils.unregister_class(OBJECT_OT_bone_center_from_selection)
    bpy.utils.unregister_class(MoveSubdivToBottomOperator)
    bpy.utils.unregister_class(OBJECT_OT_toggle_selectable)
    bpy.utils.unregister_class(ReplaceTexturePathsOperator)
    
    del bpy.types.Scene.bones_from_selection_length
    del bpy.types.Scene.bones_from_selection_use_normal
    del bpy.types.Scene.ac_target_object
    del bpy.types.Scene.ac_armature_object
    del bpy.types.Scene.ac_bone_name
    
    bpy.utils.unregister_class(REMOVE_BONE_CUSTOM_PROP_OT_operator)
    del bpy.types.Scene.remove_bone_prop_name


if __name__ == "__main__":
    register()
