cmake_minimum_required(VERSION 3.21)
project(w124_cluster_qt LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(Qt6 6.5 REQUIRED COMPONENTS Quick LabsSettings)

# Qt6::Multimedia is required on Pi (GStreamer backend for CarPlay VideoOutput).
# It is optional on Windows dev machines where CarPlay is never active.
find_package(Qt6 OPTIONAL_COMPONENTS Multimedia)

qt_standard_project_setup(REQUIRES 6.5)

qt_add_executable(w124_cluster
    src/main.cpp
    src/VehicleState.cpp
)

target_include_directories(w124_cluster PRIVATE src)

qt_add_qml_module(w124_cluster
    URI W124Cluster
    VERSION 1.0
    QML_FILES
        qml/Main.qml
        qml/DialFace.qml
        qml/DialBackground.qml
        qml/DialScale.qml
        qml/Needle.qml
        qml/MainArea.qml
        qml/mainarea/pages/ClassicPage.qml
        qml/mainarea/pages/MusicPage.qml
        qml/mainarea/pages/MapPage.qml
        qml/mainarea/pages/CarPlayVideo.qml
        qml/mainarea/classic/OdometerDisplay.qml
        qml/mainarea/classic/TripDisplay.qml
        qml/mainarea/classic/HundredMeterCounter.qml
        qml/mainarea/map/DigitalSpeedReadout.qml
        qml/mainarea/carousel/ModeCarousel.qml
        qml/SpeedoGauge.qml
        qml/SettingsPanel.qml
    RESOURCES
        assets/images/speedo_logo.png
)

target_sources(w124_cluster PRIVATE
    src/VehicleState.h
)

target_link_libraries(w124_cluster PRIVATE Qt6::Quick Qt6::LabsSettings)
if(Qt6Multimedia_FOUND)
    target_link_libraries(w124_cluster PRIVATE Qt6::Multimedia)
    target_compile_definitions(w124_cluster PRIVATE HAVE_QT_MULTIMEDIA)
endif()

install(TARGETS w124_cluster
    RUNTIME DESTINATION bin
)
