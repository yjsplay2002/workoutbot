import Foundation

struct AppSummary: Codable {
    let userId: Int
    let name: String
    let date: String
    let today: TodaySummary
    let primaryGoal: PrimaryGoal?
    let deficit: DeficitSummary
    let recentRecords: [WorkoutRecord]
}

struct TodaySummary: Codable {
    let intakeKcal: Double?
    let exerciseKcal: Double?
    let targetKcal: Double?
    let tdee: Double?
    let proteinG: Double?
    let carbsG: Double?
    let fatG: Double?
    let macros: MacroTargets?
}

struct MacroTargets: Codable {
    let direction: String?
    let proteinG: Double?
    let carbsG: Double?
    let fatG: Double?
    let proteinPct: Double?
    let carbsPct: Double?
    let fatPct: Double?
}

struct PrimaryGoal: Codable {
    let metric: String
    let targetValue: Double?
    let targetDate: String?
}

struct DeficitSummary: Codable {
    let available: Bool
    let reason: String?
    let direction: String?
    let label: String?
    let unit: String?
    let currentValue: Double?
    let targetValue: Double?
    let daysLeft: Int?
    let totalNeeded: Double?
    let dailyTarget: Double?
    let actualCumulative: Double?
    let exerciseTotal: Double?
    let achievementPct: Double?
    let measuredDays: Int?
    let targetDate: String?
}

struct WorkoutRecord: Codable, Identifiable, Hashable {
    let id: Int
    let date: String?
    let category: String?
    let structuredMd: String?
    let analysis: String?
    let estimatedKcal: Double?
    let createdAt: String?
}

