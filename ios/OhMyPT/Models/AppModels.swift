import Foundation

struct AppSummary: Codable {
    let userId: Int
    let name: String
    let date: String
    let today: TodaySummary
    let primaryGoal: PrimaryGoal?
    let deficit: DeficitSummary
    let recentRecords: [WorkoutRecord]
    let plan: DailyPlanPayload?
    let dailySummary: DailyCoachSummary?
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
    let merged: Bool?
}

// MARK: - Write / analysis results

struct AnalysisResult: Codable {
    let ok: Bool?
    let intent: String?
    let message: String?
    let error: String?
    let confidence: Double?
    let reasonMd: String?
    let records: [WorkoutRecord]?
    let meals: [MealRecord]?
    let inbody: InbodySnapshot?

    var isSuccess: Bool { ok == true }

    var displayTitle: String {
        switch (intent ?? "").lowercased() {
        case "workout": return "운동 기록"
        case "meal": return "식단 기록"
        case "inbody": return "인바디"
        case "unrelated": return "분류 불가"
        default: return "분석 결과"
        }
    }

    var displayMessage: String {
        if let message, !message.isEmpty { return message }
        if let error, !error.isEmpty { return error }
        return isSuccess ? "저장되었습니다." : "처리에 실패했습니다."
    }
}

struct MealRecord: Codable, Hashable {
    let id: Int?
    let mealType: String?
    let structuredMd: String?
    let analysisMd: String?
    let itemsMd: String?
    let estimatedKcal: Double?
    let proteinG: Double?
    let carbsG: Double?
    let fatG: Double?
    let date: String?

    var rowID: String {
        if let id { return "meal-\(id)" }
        return "meal-\(mealType ?? "x")-\(date ?? "")-\(estimatedKcal ?? 0)"
    }
}

struct InbodySnapshot: Codable, Hashable {
    let id: Int?
    let measuredAt: String?
    let weightKg: Double?
    let skeletalMuscleKg: Double?
    let bodyFatKg: Double?
    let bodyFatPct: Double?
    let bmi: Double?
    let bmrKcal: Double?
    let bodyWaterKg: Double?
    let proteinKg: Double?
    let mineralKg: Double?
    let visceralFatLevel: Double?
}

// MARK: - Plan / coach summary

struct DailyPlanPayload: Codable, Hashable {
    let ok: Bool?
    let date: String?
    let targetKcalIntake: Double?
    let targetKcalBurn: Double?
    let breakfastSuggestion: String?
    let lunchSuggestion: String?
    let dinnerSuggestion: String?
    /// Nested LLM JSON is intentionally not strongly typed (items shape varies).
    /// Prefer HTML suggestion fields for display; use this for rationale if present.
    let fullPlanRaw: String?
    let cached: Bool?
    let error: String?

    var isSuccess: Bool { ok != false && error == nil }

    var rationaleText: String? {
        guard let raw = fullPlanRaw,
              let data = raw.data(using: .utf8),
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return nil }
        return object["rationale_md"] as? String
    }

    private enum CodingKeys: String, CodingKey {
        case ok, date
        case targetKcalIntake
        case targetKcalBurn
        case breakfastSuggestion
        case lunchSuggestion
        case dinnerSuggestion
        case fullPlanRaw
        case fullPlan
        case cached, error
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        ok = try c.decodeIfPresent(Bool.self, forKey: .ok)
        date = try c.decodeIfPresent(String.self, forKey: .date)
        targetKcalIntake = try Self.decodeFlexibleDouble(c, forKey: .targetKcalIntake)
        targetKcalBurn = try Self.decodeFlexibleDouble(c, forKey: .targetKcalBurn)
        breakfastSuggestion = try c.decodeIfPresent(String.self, forKey: .breakfastSuggestion)
        lunchSuggestion = try c.decodeIfPresent(String.self, forKey: .lunchSuggestion)
        dinnerSuggestion = try c.decodeIfPresent(String.self, forKey: .dinnerSuggestion)
        cached = try c.decodeIfPresent(Bool.self, forKey: .cached)
        error = try c.decodeIfPresent(String.self, forKey: .error)

        if let raw = try c.decodeIfPresent(String.self, forKey: .fullPlanRaw) {
            fullPlanRaw = raw
        } else if let dict = try? c.decodeIfPresent([String: JSONValue].self, forKey: .fullPlan),
                  let data = try? JSONEncoder().encode(dict),
                  let str = String(data: data, encoding: .utf8) {
            fullPlanRaw = str
        } else if let rawObject = try? c.decodeIfPresent(JSONValue.self, forKey: .fullPlan),
                  let data = try? JSONEncoder().encode(rawObject),
                  let str = String(data: data, encoding: .utf8) {
            fullPlanRaw = str
        } else {
            fullPlanRaw = nil
        }
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encodeIfPresent(ok, forKey: .ok)
        try c.encodeIfPresent(date, forKey: .date)
        try c.encodeIfPresent(targetKcalIntake, forKey: .targetKcalIntake)
        try c.encodeIfPresent(targetKcalBurn, forKey: .targetKcalBurn)
        try c.encodeIfPresent(breakfastSuggestion, forKey: .breakfastSuggestion)
        try c.encodeIfPresent(lunchSuggestion, forKey: .lunchSuggestion)
        try c.encodeIfPresent(dinnerSuggestion, forKey: .dinnerSuggestion)
        try c.encodeIfPresent(fullPlanRaw, forKey: .fullPlanRaw)
        try c.encodeIfPresent(cached, forKey: .cached)
        try c.encodeIfPresent(error, forKey: .error)
    }

    private static func decodeFlexibleDouble(
        _ c: KeyedDecodingContainer<CodingKeys>,
        forKey key: CodingKeys
    ) throws -> Double? {
        if let d = try c.decodeIfPresent(Double.self, forKey: key) { return d }
        if let i = try c.decodeIfPresent(Int.self, forKey: key) { return Double(i) }
        if let s = try c.decodeIfPresent(String.self, forKey: key), let d = Double(s) { return d }
        return nil
    }
}

/// Minimal JSON tree for lossless re-encoding of untyped objects.
enum JSONValue: Codable, Hashable {
    case string(String)
    case number(Double)
    case bool(Bool)
    case object([String: JSONValue])
    case array([JSONValue])
    case null

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let b = try? container.decode(Bool.self) {
            self = .bool(b)
        } else if let i = try? container.decode(Int.self) {
            self = .number(Double(i))
        } else if let d = try? container.decode(Double.self) {
            self = .number(d)
        } else if let s = try? container.decode(String.self) {
            self = .string(s)
        } else if let o = try? container.decode([String: JSONValue].self) {
            self = .object(o)
        } else if let a = try? container.decode([JSONValue].self) {
            self = .array(a)
        } else {
            self = .null
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .string(let s): try container.encode(s)
        case .number(let n): try container.encode(n)
        case .bool(let b): try container.encode(b)
        case .object(let o): try container.encode(o)
        case .array(let a): try container.encode(a)
        case .null: try container.encodeNil()
        }
    }
}

struct DailyCoachSummary: Codable, Hashable {
    let ok: Bool?
    let date: String?
    let summaryMd: String?
    let goalAssessmentMd: String?
    let cached: Bool?
    let error: String?

    var isSuccess: Bool { ok != false && error == nil }
}

// MARK: - Weekly stats (client-side)

struct DayStat: Identifiable, Hashable {
    let id: String
    let date: String
    let label: String
    let workoutKcal: Double
    let sessionCount: Int
}
