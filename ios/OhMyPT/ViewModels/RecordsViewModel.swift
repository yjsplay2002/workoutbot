import Foundation

@MainActor
final class RecordsViewModel: ObservableObject {
    @Published private(set) var records: [WorkoutRecord] = []
    @Published private(set) var isLoading = false
    @Published var errorMessage: String?

    func load(configuration: AppConfiguration) async {
        guard configuration.isValid else {
            errorMessage = "설정에서 서버 URL과 user_id를 입력해 주세요."
            records = []
            return
        }

        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            records = try await APIClient(configuration: configuration).fetchRecords(limit: 20)
        } catch {
            records = []
            errorMessage = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }
}

