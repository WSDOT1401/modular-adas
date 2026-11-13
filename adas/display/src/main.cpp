// ADAS display — shows the modular ADAS's alerts on a round (up to 720×720)
// or 4:3 (960×720) screen. Data arrives as UDP JSON (see adas/protocol); this
// program never talks to hardware itself.

#include <QCommandLineParser>
#include <QCursor>
#include <QDir>
#include <QFileInfo>
#include <QFontDatabase>
#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QScreen>
#include <cstdio>

#include "AdasState.h"

// The UI font (B612, made for cockpit displays) is built into the binary from
// assets/fonts/ (see CMakeLists.txt). Returns its family, or "" if none is
// embedded, in which case the system font is used.
static QString loadBundledFont() {
    const QDir dir(QStringLiteral(":/fonts"));
    QString family;
    for (const QFileInfo& fi : dir.entryInfoList({"*.ttf", "*.otf"}, QDir::Files, QDir::Name)) {
        const int id = QFontDatabase::addApplicationFont(fi.absoluteFilePath());
        if (id < 0) {
            qWarning("could not load font %s", qPrintable(fi.fileName()));
            continue;
        }
        const QStringList fams = QFontDatabase::applicationFontFamilies(id);
        if (family.isEmpty() && !fams.isEmpty()) family = fams.first();
    }
    return family;
}

// Which monitor to use. `spec` is an output name as --list-screens prints it
// (e.g. HDMI-A-2), a screen number, or "auto": with more than one monitor,
// the first square one (a round panel reports itself as square), else the
// primary. Returns an index into QGuiApplication::screens(), or -1.
static int pickScreen(const QString& spec) {
    const QList<QScreen*> screens = QGuiApplication::screens();
    if (spec != QLatin1String("auto")) {
        for (int i = 0; i < screens.size(); ++i)
            if (screens[i]->name() == spec) return i;
        bool isNumber = false;
        const int n = spec.toInt(&isNumber);
        if (isNumber && n >= 0 && n < screens.size()) return n;
        return -1;
    }
    if (screens.size() > 1) {
        for (int i = 0; i < screens.size(); ++i) {
            const QSize s = screens[i]->size();
            if (s.width() == s.height()) return i;
        }
    }
    return screens.indexOf(QGuiApplication::primaryScreen());
}

int main(int argc, char* argv[]) {
    QGuiApplication app(argc, argv);
    QGuiApplication::setOrganizationName(QStringLiteral("modular-adas"));
    QGuiApplication::setApplicationName(QStringLiteral("adas-display"));

    QCommandLineParser cli;
    cli.setApplicationDescription(QStringLiteral("Modular ADAS display"));
    cli.addHelpOption();
    const QCommandLineOption portOpt("port", "UDP port to listen on (default 9100).", "port", "9100");
    const QCommandLineOption controlPortOpt("control-port",
        "UDP port the vision service takes the driver's feature choices on (default 9102; 0 = don't send).",
        "port", "9102");
    const QCommandLineOption shapeOpt("shape", "Screen shape: round or rect. Overrides the saved setting.", "shape");
    const QCommandLineOption windowedOpt("windowed", "Run in a window instead of full screen.");
    const QCommandLineOption scenarioOpt("scenario",
        "Play a built-in scenario instead of waiting for data: cruise, lane_left, lane_right, "
        "fcw, overspeed, new_sign, fault, feature_off, following, or cycle.", "name");
    const QCommandLineOption snapshotOpt("snapshot", "Save the screen to a PNG after start-up, then quit.", "file");
    const QCommandLineOption screenOpt("screen",
        "Monitor to run on: an output name from --list-screens (e.g. HDMI-A-2), a number, "
        "or auto (default: the square monitor when there are several).", "name", "auto");
    const QCommandLineOption listScreensOpt("list-screens", "Print the connected monitors and quit.");
    cli.addOptions({portOpt, controlPortOpt, shapeOpt, windowedOpt, scenarioOpt, snapshotOpt, screenOpt, listScreensOpt});
    cli.process(app);

    const QList<QScreen*> screens = QGuiApplication::screens();
    if (cli.isSet(listScreensOpt)) {
        for (int i = 0; i < screens.size(); ++i) {
            const QScreen* s = screens[i];
            std::printf("%d  %-12s %dx%d%s\n", i, qPrintable(s->name()), s->size().width(),
                        s->size().height(), s == QGuiApplication::primaryScreen() ? "  (primary)" : "");
        }
        return 0;
    }
    const int screenIndex = pickScreen(cli.value(screenOpt));
    if (screenIndex < 0) {
        qCritical("--screen %s: no such monitor (see --list-screens)", qPrintable(cli.value(screenOpt)));
        return 2;
    }

    const QString shape = cli.value(shapeOpt);
    if (!shape.isEmpty() && shape != QLatin1String("round") && shape != QLatin1String("rect")) {
        qCritical("--shape must be round or rect");
        return 2;
    }

    // Every letter on screen is a capital: easier to read at a glance.
    const QString family = loadBundledFont();
    QFont f = family.isEmpty() ? QGuiApplication::font() : QFont(family);
    f.setCapitalization(QFont::AllUppercase);
    QGuiApplication::setFont(f);

    // A scripted scenario must not mix with a running producer, so it does not
    // listen. A snapshot alone does: it shows whatever arrives over UDP.
    const bool offline = cli.isSet(scenarioOpt);
    const quint16 port = offline ? 0 : static_cast<quint16>(cli.value(portOpt).toUInt());
    AdasState state(port, static_cast<quint16>(cli.value(controlPortOpt).toUInt()));

#ifdef Q_OS_LINUX
    const bool fullScreen = !cli.isSet(windowedOpt) && !cli.isSet(snapshotOpt);
#else
    const bool fullScreen = false;  // desktop development
#endif
    // Full screen on the ADAS monitor: no pointer wandering over from the
    // desktop monitor.
    if (fullScreen) QGuiApplication::setOverrideCursor(Qt::BlankCursor);

    QQmlApplicationEngine engine;
    QQmlContext* ctx = engine.rootContext();
    ctx->setContextProperty(QStringLiteral("adas"), &state);
    ctx->setContextProperty(QStringLiteral("startupShape"), shape);
    ctx->setContextProperty(QStringLiteral("startFullScreen"), fullScreen);
    ctx->setContextProperty(QStringLiteral("startupScreen"), screenIndex);
    ctx->setContextProperty(QStringLiteral("startupScenario"), cli.value(scenarioOpt));
    ctx->setContextProperty(QStringLiteral("snapshotPath"),
                            cli.isSet(snapshotOpt) ? QFileInfo(cli.value(snapshotOpt)).absoluteFilePath()
                                                   : QString());

    QObject::connect(&engine, &QQmlApplicationEngine::objectCreationFailed, &app,
                     []() { QCoreApplication::exit(1); }, Qt::QueuedConnection);
    engine.loadFromModule("AdasDisplay", "Main");

    return app.exec();
}
