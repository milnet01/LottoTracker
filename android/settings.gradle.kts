// The Android app (LOTTO-0106 §4.1). Built by tools/build_apk.sh inside
// packaging/Containerfile.android; see that script for the toolchain pins.
pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}
rootProject.name = "LottoTracker"
include(":app")
