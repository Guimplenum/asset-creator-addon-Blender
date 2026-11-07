# asset-creator-addon-Blender

**Asset Creator** — аддон для Blender, предназначенный для автоматизации рабочего процесса подготовки 3D-ассетов, организации структуры сцены, моделинга и риггинга.

YouTube - https://youtu.be/K4Bx2IO7Nhk

Аддон предоставляет набор инструментов для создания стандартной иерархии коллекций, автоматического именования объектов и данных, настройки модификаторов, создания простых ригов и проверки технического качества ассетов.
Панель разделена на несколько блоков для удобства и разных задач.
Это студийный аддон для работы, поэтому он жестко привязан к названию файла .blend на английском, четкому, такому же названию основной коллекции, где будет лежать объекты с суффиксом_main, в котором в свою очередь должна лежать коллекция _geo

<img width="1920" height="1080" alt="Снимок экрана — 2026-11-07 в 17 46 46" src="https://github.com/user-attachments/assets/3c620e6e-becf-4f0b-8808-89fa7b1eaa08" />

Основные возможности

Asset Organization — автоматическое создание структуры коллекций и переименование объектов, мешей и материалов по заданным правилам.

Modeling Tools — применение трансформаций, настройка Shade Smooth, управление уровнями Subdivision Surface и другие инструменты для работы с геометрией.

Rigging Tools — создание простого рига с автоматической привязкой геометрии, создание костей по выбранным вершинам, настройка контроллеров и управление видимостью объектов через свойства костей.

Modeling Validation — проверка геометрии, топологии, трансформаций, модификаторов, структуры коллекций и других параметров модели.

Rig Validation — проверка структуры рига, именования костей, настроек позы, контроллеров и других технических требований.

Scene Cleanup — очистка неиспользуемых данных, удаление анимации и сброс 3D-курсора.

Texture Management — управление путями текстур и организация текстурных файлов.

Scene Tools — дополнительные инструменты для проверки и подготовки сцены.

Все инструменты собраны в одной панели 3D Viewport → N-Panel → Assets.

 English

Asset Tools is a Blender add-on designed to streamline 3D asset preparation, scene organization, modeling, and rigging workflows.

It provides a collection of tools for automatically creating collection hierarchies, managing object and data naming conventions, configuring modifiers, generating simple rigs, and validating technical asset requirements.
The panel is divided into several blocks for convenience and different tasks. 

Since this is a studio workflow addon, it strictly requires:
1. A clear **English name** for the `.blend` file.
2. The **main collection** named exactly the same as the file.
3. Objects inside it must have the `_main` suffix.
4. A nested `_geo` collection inside the main one.


Main Features

Asset Organization — automatically creates collection hierarchies and renames objects, meshes, and materials according to predefined naming conventions.

Modeling Tools — applies object transforms, sets Shade Smooth, manages Subdivision Surface levels, and provides additional geometry workflow utilities.

Rigging Tools — generates simple rigs with automatic mesh binding, creates bones from selected vertices, configures controllers, and manages object visibility through bone properties.

Modeling Validation — checks geometry, topology, transforms, modifiers, collection hierarchy, and other modeling requirements.

Rig Validation — checks rig structure, bone naming, pose settings, controllers, and other technical requirements.

Scene Cleanup — removes unused data, clears animation data, and resets the 3D cursor.

Texture Management — manages texture paths and organizes texture files.

Scene Tools — additional utilities for scene inspection and asset preparation.

All tools are accessible from a single panel in 3D Viewport → N-Panel → Assets.
