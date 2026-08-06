import SwiftUI

struct RootView: View {
    @AppStorage(AppDefaults.Key.baseURL) private var baseURL = AppDefaults.defaultBaseURL
    @AppStorage(AppDefaults.Key.userID) private var userIDText = ""
    @AppStorage(AppDefaults.Key.appToken) private var appToken = ""

    private var configuration: AppConfiguration {
        AppConfiguration(baseURL: baseURL, userIDText: userIDText, appToken: appToken)
    }

    var body: some View {
        if configuration.isValid {
            TabView {
                ChatView(configuration: configuration)
                    .tabItem {
                        Label("코치", systemImage: "bubble.left.and.text.bubble.right.fill")
                    }

                TodayView(configuration: configuration)
                    .tabItem {
                        Label("오늘", systemImage: "chart.pie.fill")
                    }

                RecordsView(configuration: configuration)
                    .tabItem {
                        Label("기록", systemImage: "list.bullet.rectangle")
                    }

                NavigationStack {
                    SettingsView()
                }
                .tabItem {
                    Label("프로필", systemImage: "person.crop.circle")
                }
            }
            .tint(OMP.ink)
        } else {
            NavigationStack {
                SettingsView(showOnboardingMessage: true)
            }
        }
    }
}
