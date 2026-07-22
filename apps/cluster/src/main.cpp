#include <QGuiApplication>
#include <QDir>
#include <QFileInfo>
#include <QFontDatabase>
#include <QQmlApplicationEngine>
#include <QQmlContext>

#include "VehicleState.h"

static QString detectDefaultUiFont() {
#ifdef Q_OS_WIN
    return QStringLiteral("Segoe UI");
#elif defined(Q_OS_LINUX)
    return QStringLiteral("Noto Sans");
#else
    return QStringLiteral("Sans Serif");
#endif
}

static QString loadBundledFontFamily() {
    const QString appDir = QCoreApplication::applicationDirPath();
    const QString cwd = QDir::currentPath();

    const QStringList baseDirs = {
        appDir + "/assets/fonts",
        appDir + "/../assets/fonts",
        cwd + "/assets/fonts",
        cwd + "/../assets/fonts",
        cwd + "/apps/cluster/assets/fonts"
    };

    const QStringList candidates = {
        QStringLiteral("Futura.ttf"),
        QStringLiteral("Futura.otf"),
        QStringLiteral("Futura-Medium.ttf"),
        QStringLiteral("Futura-Book.ttf"),
        QStringLiteral("FuturaPTBook.otf"),
        QStringLiteral("FuturaPTMedium.otf"),
        QStringLiteral("FuturaStd-Book.otf")
    };

    for (const QString& dirPath : baseDirs) {
        for (const QString& fileName : candidates) {
            const QString fullPath = QDir(dirPath).filePath(fileName);
            if (!QFileInfo::exists(fullPath)) {
                continue;
            }
            const int id = QFontDatabase::addApplicationFont(fullPath);
            if (id < 0) {
                continue;
            }
            const QStringList families = QFontDatabase::applicationFontFamilies(id);
            if (!families.isEmpty()) {
                return families.first();
            }
        }
    }

    return QString();
}

int main(int argc, char* argv[]) {
    QGuiApplication app(argc, argv);

    QCoreApplication::setOrganizationName(QStringLiteral("Zeigertechnik"));
    QCoreApplication::setOrganizationDomain(QStringLiteral("local.zeigertechnik"));
    QCoreApplication::setApplicationName(QStringLiteral("w124_cluster"));

    VehicleState vehicleState;

    const QStringList args = QCoreApplication::arguments();
    for (const QString& arg : args) {
        if (arg == "--state") {
            vehicleState.setSource("state");
        } else if (arg == "--udp") {
            vehicleState.setSource("udp");
        } else if (arg.startsWith("--udp-port=")) {
            vehicleState.setUdpPort(arg.mid(QString("--udp-port=").size()).toInt());
        } else if (arg.startsWith("--state-file=")) {
            vehicleState.setStateFile(arg.mid(QString("--state-file=").size()));
        } else if (arg.startsWith("--poll-ms=")) {
            vehicleState.setPollMs(arg.mid(QString("--poll-ms=").size()).toInt());
        } else if (arg.startsWith("--max-speed=")) {
            vehicleState.setProfileMaxSpeed(arg.mid(QString("--max-speed=").size()).toInt());
        } else if (arg.startsWith("--unit=")) {
            vehicleState.setProfileUnit(arg.mid(QString("--unit=").size()));
        }
    }

    QString uiFontFamily = loadBundledFontFamily();
    if (uiFontFamily.isEmpty()) {
        uiFontFamily = detectDefaultUiFont();
    }

    QQmlApplicationEngine engine;
    engine.rootContext()->setContextProperty("vehicleState", &vehicleState);
    engine.rootContext()->setContextProperty("uiFontFamily", uiFontFamily);

    QObject::connect(
        &engine,
        &QQmlApplicationEngine::objectCreationFailed,
        &app,
        []() { QCoreApplication::exit(-1); },
        Qt::QueuedConnection
    );

    engine.loadFromModule("W124Cluster", "Main");
    return app.exec();
}
