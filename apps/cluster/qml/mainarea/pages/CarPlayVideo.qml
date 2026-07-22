// CarPlay video component — loaded only when Qt Multimedia is available.
// MapPage uses a Loader so this fails gracefully on platforms without the module.

import QtQuick
import QtMultimedia

Item {
    id: root

    // Exposed so MapPage can drive the overlay visibility
    readonly property bool isPlaying: player.playbackState === MediaPlayer.PlayingState

    MediaPlayer {
        id: player
        // GStreamer pipeline: Qt reads raw H264 from the carplay server TCP socket
        source: "gst-pipeline: tcpclientsrc host=127.0.0.1 port=9001 " +
                "! h264parse ! avdec_h264 ! videoconvert ! appsink name=qtvideosink"
        videoOutput: video
        audioOutput: AudioOutput { volume: 1.0 }
    }

    VideoOutput {
        id: video
        anchors.fill: parent
    }
}
