import Foundation

@MainActor
final class TodayViewModel: ObservableObject {
    @Published private(set) var summary: AppSummary?
    @Published private(set) var plan: DailyPlanPayload?
    @Published private(set) var coachSummary: DailyCoachSummary?
    @Published private(set) var isLoading = false
    @Published private(set) var isGeneratingPlan = false
    @Published private(set) var isGeneratingSummary = false
    @Published var errorMessage: String?
    @Published var actionMessage: String?

    func load(configuration: AppConfiguration) async {
        guard configuration.isValid else {
            errorMessage = "설정에서 서버 URL과 user_id를 입력해 주세요."
            summary = nil
            plan = nil
            coachSummary = nil
            return
        }

        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            let loaded = try await APIClient(configuration: configuration).fetchSummary()
            summary = loaded
            plan = loaded.plan
            coachSummary = loaded.dailySummary
        } catch {
            summary = nil
            errorMessage = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }

    func generatePlan(configuration: AppConfiguration, refresh: Bool) async {
        guard configuration.isValid else {
            actionMessage = "설정을 먼저 완료해 주세요."
            return
        }

        isGeneratingPlan = true
        actionMessage = nil
        defer { isGeneratingPlan = false }

        do {
            let result = try await APIClient(configuration: configuration).generatePlan(refresh: refresh)
            if let error = result.error, result.ok == false {
                actionMessage = error
                return
            }
            plan = result
            actionMessage = result.cached == true ? "저장된 플랜을 불러왔습니다." : "오늘의 플랜을 생성했습니다."
        } catch {
            actionMessage = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }

    func generateCoachSummary(configuration: AppConfiguration, refresh: Bool) async {
        guard configuration.isValid else {
            actionMessage = "설정을 먼저 완료해 주세요."
            return
        }

        isGeneratingSummary = true
        actionMessage = nil
        defer { isGeneratingSummary = false }

        do {
            let result = try await APIClient(configuration: configuration).generateDailySummary(refresh: refresh)
            if let error = result.error, result.ok == false {
                actionMessage = error
                return
            }
            coachSummary = result
            actionMessage = result.cached == true ? "저장된 요약을 불러왔습니다." : "오늘 요약을 생성했습니다."
        } catch {
            actionMessage = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }
}
