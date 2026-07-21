import Foundation

@MainActor
final class RecordsViewModel: ObservableObject {
    @Published private(set) var records: [WorkoutRecord] = []
    @Published private(set) var weeklyStats: [DayStat] = []
    @Published private(set) var weekWorkoutKcal: Double = 0
    @Published private(set) var weekSessionCount: Int = 0
    @Published private(set) var isLoading = false
    @Published var errorMessage: String?

    func load(configuration: AppConfiguration) async {
        guard configuration.isValid else {
            errorMessage = "설정에서 서버 URL과 user_id를 입력해 주세요."
            records = []
            weeklyStats = []
            weekWorkoutKcal = 0
            weekSessionCount = 0
            return
        }

        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            let loaded = try await APIClient(configuration: configuration).fetchRecords(limit: 50)
            records = loaded
            recomputeWeekly(from: loaded)
        } catch {
            records = []
            weeklyStats = []
            weekWorkoutKcal = 0
            weekSessionCount = 0
            errorMessage = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }

    private func recomputeWeekly(from records: [WorkoutRecord]) {
        let calendar = Calendar(identifier: .gregorian)
        let today = calendar.startOfDay(for: Date())
        let formatter = DateFormatter()
        formatter.calendar = calendar
        formatter.locale = Locale(identifier: "ko_KR")
        formatter.dateFormat = "yyyy-MM-dd"

        let short = DateFormatter()
        short.calendar = calendar
        short.locale = Locale(identifier: "ko_KR")
        short.dateFormat = "E"

        var stats: [DayStat] = []
        var totalKcal: Double = 0
        var totalSessions = 0

        for offset in (0..<7).reversed() {
            guard let day = calendar.date(byAdding: .day, value: -offset, to: today) else { continue }
            let key = formatter.string(from: day)
            let dayRecords = records.filter { $0.date == key }
            let kcal = dayRecords.compactMap(\.estimatedKcal).reduce(0, +)
            let count = dayRecords.count
            totalKcal += kcal
            totalSessions += count
            stats.append(DayStat(
                id: key,
                date: key,
                label: short.string(from: day),
                workoutKcal: kcal,
                sessionCount: count
            ))
        }

        weeklyStats = stats
        weekWorkoutKcal = totalKcal
        weekSessionCount = totalSessions
    }
}
