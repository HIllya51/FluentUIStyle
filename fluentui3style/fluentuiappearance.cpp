#include "fluentuiappearance.h"

#include "fluentui3style.h"
#include "qapplication.h"
#include "palettemanager.h"
#include "qdebug.h"
#include "qsettings.h"

#include <QStyleHints>
#include <QPalette>

#ifdef Q_OS_WIN
#include <windows.h>
#endif

class FluentUIAppearancePrivate
{
public:
    void applyTheme();
    void updateTitleBar();
    bool isSystemDark();

    Theme theme{Theme::Light};
    QWidget* mainWindow{nullptr};
};

FluentUIAppearance::FluentUIAppearance(QObject *parent)
    : QObject{parent}, d_ptr(new FluentUIAppearancePrivate)
{}

FluentUIAppearance &FluentUIAppearance::instance()
{
    static FluentUIAppearance inst;
    return inst;
}

void FluentUIAppearance::initialize()
{
    Q_D(FluentUIAppearance);
    setTheme(d->isSystemDark() ? Theme::Dark : Theme::Light);
}

void FluentUIAppearance::setTheme(Theme theme)
{
    Q_D(FluentUIAppearance);

    qDebug()<< "Setting theme to:" << (theme == Theme::Dark ? "Dark" : "Light");
    d->theme = theme;
    d->applyTheme();
}

Theme FluentUIAppearance::theme() const
{
    Q_D(const FluentUIAppearance);
    return d->theme;
}

void FluentUIAppearance::setMainWindow(QWidget *mainWindow)
{
    Q_D(FluentUIAppearance);
    d->mainWindow = mainWindow;
    d->updateTitleBar();
}

void FluentUIAppearancePrivate::applyTheme()
{
#if /*QT_VERSION < QT_VERSION_CHECK(6, 8, 0)*/1
    auto appPalette = qApp->palette();
    // PaletteManager::instance().setColorScheme(ColorScheme::Teams);
    PaletteManager::instance().applyPalette(appPalette, theme == Theme::Dark);
    qApp->setPalette(appPalette);
#else
    qApp->styleHints()->setColorScheme(theme == Theme::Dark ? Qt::ColorScheme::Dark : Qt::ColorScheme::Light);
#endif
    qApp->setStyle(new FluentUI3Style());
    updateTitleBar();
}

void FluentUIAppearancePrivate::updateTitleBar()
{
#if QT_VERSION < QT_VERSION_CHECK(6, 8, 0)
#ifdef Q_OS_WIN
    if (mainWindow == nullptr)
        return;

    // dwmapi 运行时动态解析：dwmapi.dll 是 Vista+ 才有（XP 上不存在），
    // 静态导入会让插件在老系统上直接加载失败
    static auto pfnDwmSetWindowAttribute = [] {
        using Fn = HRESULT(WINAPI *)(HWND, DWORD, LPCVOID, DWORD);
        HMODULE mod = GetModuleHandleW(L"dwmapi.dll");
        if (mod == nullptr)
            mod = LoadLibraryW(L"dwmapi.dll");
        return reinterpret_cast<Fn>(
            mod ? GetProcAddress(mod, "DwmSetWindowAttribute") : nullptr);
    }();
    if (pfnDwmSetWindowAttribute == nullptr)
        return;

    HWND hwnd = reinterpret_cast<HWND>(mainWindow->winId());
    BOOL darkMode = theme == Theme::Dark;
    pfnDwmSetWindowAttribute(hwnd, 20, &darkMode, sizeof(darkMode));
#endif
#endif
}

bool FluentUIAppearancePrivate::isSystemDark()
{
#ifdef Q_OS_WIN
    QSettings settings(
        "HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize",
        QSettings::NativeFormat);
    int value = settings.value("AppsUseLightTheme", 1).toInt();

    return value == 0;

#else
    return false;
#endif
}
