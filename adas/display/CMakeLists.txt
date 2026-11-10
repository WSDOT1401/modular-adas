cmake_minimum_required(VERSION 3.21)
project(adas_display LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Same floor as the W124 cluster. QtQuick.Shapes and QtCore (Settings) are
# QML modules from qtdeclarative; on Raspberry Pi OS install
# qml6-module-qtquick-shapes and qml6-module-qtcore (see README.md).
find_package(Qt6 6.5 REQUIRED COMPONENTS Quick Network)

qt_standard_project_setup(REQUIRES 6.5)

qt_add_executable(adas_display
    src/main.cpp
    src/AdasState.cpp
    src/AdasState.h
)

target_include_directories(adas_display PRIVATE src)

set(QML_SOURCES
    qml/Main.qml
    qml/Theme.qml
    qml/RoundLayout.qml
    qml/RectLayout.qml
    qml/LaneView.qml
    qml/CarRear.qml
    qml/SignIcon.qml
    qml/AlertIcon.qml
    qml/SettingsMenu.qml
    qml/Scenarios.js
)

# Serve the files at the module root, next to its qmldir. Left under qml/,
# each file's implicit directory import would shadow the module and the
# Theme singleton would resolve as a plain type.
foreach(qml_file IN LISTS QML_SOURCES)
    get_filename_component(qml_name ${qml_file} NAME)
    set_source_files_properties(${qml_file} PROPERTIES QT_RESOURCE_ALIAS ${qml_name})
endforeach()

set_source_files_properties(qml/Theme.qml PROPERTIES QT_QML_SINGLETON_TYPE TRUE)

qt_add_qml_module(adas_display
    URI AdasDisplay
    VERSION 1.0
    QML_FILES ${QML_SOURCES}
)

target_link_libraries(adas_display PRIVATE Qt6::Quick Qt6::Network)

install(TARGETS adas_display RUNTIME DESTINATION bin)
