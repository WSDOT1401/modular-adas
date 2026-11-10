// ADAS display — shows the modular ADAS's alerts on a round (up to 720×720)
// or 4:3 (960×720) screen. Data arrives as UDP JSON (see adas/protocol); this
// program never talks to hardware itself.

#include <QCommandLineParser>
#include <QDir>
#include <QFileInfo>
#include <QFontDatabase>
#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQmlContext>

#include "AdasState.h"

// The design uses Jost (a free Futura-like face); a Futura file works too.
// Drop a .ttf/.otf into assets/fonts/ next to the binary or the source tree.
static QString loadBundledFont() {
    const QString appDir = QCoreApplication::applicationDirPath();
    const QStringList dirs = {
        appDir + "/assets/fonts",
        appDir + "/../assets/fonts",
        QDir::currentPath() + "/assets/fonts",
    };
    const QStringList patterns = {"Jost*.ttf", "Jost*.otf", "Futura*.ttf", "Futura*.otf"};
    QString family;
    for (const QString& dirPath : dirs) {
        const QDir dir(dirPath);
        for (const QFileInfo& fi : dir.entryInfoList(patterns, QDir::Files, QDir::Name)) {
            const int id = QFontDatabase::addApplicationFont(fi.absoluteFilePath());
            const QStringList fams = QFontDatabase::applicationFontFamilies(id);
            if (family.isEmpty() && !fams.isEmpty()) family = fams.first();
        }
        if (!family.isEmpty()) return family;
    }
    return QString();
}

int main(int argc, char* argv[]) {
    QGuiApplication app(argc, argv);
    QGuiApplication::setOrganizationName(QStringLiteral("modular-adas"));
    QGuiApplication::setApplicationName(QStringLiteral("adas-display"));

    QCommandLineParser cli;
    cli.setApplicationDescription(QStringLiteral("Modular ADAS display"));
    cli.addHelpOption();
    const QCommandLineOption portOpt("port", "UDP port to listen on (default 9100).", "port", "9100");
    const QCommandLineOption shapeOpt("shape", "Screen shape: round or rect. Overrides the saved setting.", "shape");
    const QCommandLineOption windowedOpt("windowed", "Run in a window instead of full screen.");
    const QCommandLineOption scenarioOpt("scenario",
        "Play a built-in scenario instead of waiting for data: cruise, lane_left, lane_right, "
        "fcw, overspeed, new_sign, fault, or cycle.", "name");
    const QCommandLineOption snapshotOpt("snapshot", "Save the screen to a PNG after start-up, then quit.", "file");
    cli.addOptions({portOpt, shapeOpt, windowedOpt, scenarioOpt, snapshotOpt});
    cli.process(app);

    const QString shape = cli.value(shapeOpt);
    if (!shape.isEmpty() && shape != QLatin1String("round") && shape != QLatin1String("rect")) {
        qCritical("--shape must be round or rect");
        return 2;
    }

    const QString family = loadBundledFont();
    if (!family.isEmpty()) {
        QFont f(family);
        QGuiApplication::setFont(f);
    }

    // A scripted scenario must not mix with a running producer, so it does not
    // listen. A snapshot alone does: it shows whatever arrives over UDP.
    const bool offline = cli.isSet(scenarioOpt);
    const quint16 port = offline ? 0 : static_cast<quint16>(cli.value(portOpt).toUInt());
    AdasState state(port);

#ifdef Q_OS_LINUX
    const bool fullScreen = !cli.isSet(windowedOpt) && !cli.isSet(snapshotOpt);
#else
    const bool fullScreen = false;  // desktop development
#endif

    QQmlApplicationEngine engine;
    QQmlContext* ctx = engine.rootContext();
    ctx->setContextProperty(QStringLiteral("adas"), &state);
    ctx->setContextProperty(QStringLiteral("startupShape"), shape);
    ctx->setContextProperty(QStringLiteral("startFullScreen"), fullScreen);
    ctx->setContextProperty(QStringLiteral("startupScenario"), cli.value(scenarioOpt));
    ctx->setContextProperty(QStringLiteral("snapshotPath"),
                            cli.isSet(snapshotOpt) ? QFileInfo(cli.value(snapshotOpt)).absoluteFilePath()
                                                   : QString());

    QObject::connect(&engine, &QQmlApplicationEngine::objectCreationFailed, &app,
                     []() { QCoreApplication::exit(1); }, Qt::QueuedConnection);
    engine.loadFromModule("AdasDisplay", "Main");

    return app.exec();
}
