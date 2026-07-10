import Foundation

@MainActor
final class TodayViewModel: ObservableObject {
    @Published private(set) var summary: AppSummary?
    @Published private(set) var isLoading = false
    @Published var errorMessage: String?

    func load(configuration: AppConfiguration) async {
        guard configuration.isValid else {
            errorMessage = "설정에서 서버 URL과 user_id를 입력해 주세요."
            summary = nil
            return
        }

        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            summary = try await APIClient(configuration: configuration).fetchSummary()
        } catch {
            summary = nil
            errorMessage = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }
}

