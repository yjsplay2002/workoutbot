import SwiftUI

struct SettingsView: View {
    var showOnboardingMessage = false

    @AppStorage(AppDefaults.Key.baseURL) private var baseURL = AppDefaults.defaultBaseURL
    @AppStorage(AppDefaults.Key.userID) private var userIDText = ""
    @AppStorage(AppDefaults.Key.appToken) private var appToken = ""

    private var configuration: AppConfiguration {
        AppConfiguration(baseURL: baseURL, userIDText: userIDText, appToken: appToken)
    }

    var body: some View {
        Form {
            if showOnboardingMessage {
                Section {
                    Label("앱을 사용하려면 서버 URL과 텔레그램 user_id가 필요합니다.", systemImage: "person.crop.circle.badge.checkmark")
                        .foregroundStyle(.secondary)
                }
            }

            Section("서버") {
                TextField("서버 URL", text: $baseURL)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .keyboardType(.URL)

                Button {
                    baseURL = AppDefaults.defaultBaseURL
                } label: {
                    Label("기본 서버로 복원", systemImage: "arrow.counterclockwise")
                }
            }

            Section("사용자") {
                TextField("텔레그램 user_id", text: numericUserIDBinding)
                    .keyboardType(.numberPad)

                SecureField("앱 토큰 (선택)", text: $appToken)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
            } footer: {
                Text("서버에 APP_API_TOKEN이 설정된 경우에만 앱 토큰을 입력하세요.")
            }

            Section {
                HStack {
                    Label(
                        configuration.isValid ? "설정 완료" : "필수 설정을 입력하세요",
                        systemImage: configuration.isValid ? "checkmark.circle.fill" : "exclamationmark.circle.fill"
                    )
                    Spacer()
                }
                .foregroundStyle(configuration.isValid ? OMP.green : OMP.red)
            }

            Section("앱 안내") {
                Label("사진·텍스트로 운동/식단/인바디를 기록합니다.", systemImage: "camera.viewfinder")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                Label("플랜·요약은 목표 등록 후 오늘 탭에서 생성합니다.", systemImage: "calendar")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
        }
        .navigationTitle("설정")
    }

    private var numericUserIDBinding: Binding<String> {
        Binding {
            userIDText
        } set: { newValue in
            userIDText = newValue.filter { $0.isNumber }
        }
    }
}

