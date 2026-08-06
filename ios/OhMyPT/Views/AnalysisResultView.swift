import SwiftUI

struct AnalysisResultView: View {
    let result: AnalysisResult
    var onDismiss: (() -> Void)?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                header

                if let records = result.records, !records.isEmpty {
                    ForEach(records) { record in
                        VStack(alignment: .leading, spacing: 10) {
                            HStack {
                                Text(record.category ?? "운동")
                                    .font(.caption.weight(.semibold))
                                    .padding(.horizontal, 9)
                                    .padding(.vertical, 5)
                                    .background(OMP.panel, in: RoundedRectangle(cornerRadius: 5, style: .continuous))
                                    .foregroundStyle(.white)
                                Text(record.date ?? "-")
                                    .font(.subheadline)
                                    .foregroundStyle(OMP.ink2)
                                if record.merged == true {
                                    Text("병합")
                                        .font(.caption2.weight(.bold))
                                        .padding(.horizontal, 8)
                                        .padding(.vertical, 4)
                                        .background(OMP.yellow, in: RoundedRectangle(cornerRadius: 5, style: .continuous))
                                        .foregroundStyle(OMP.panel)
                                }
                                Spacer()
                                Text(Formatters.kcal(record.estimatedKcal))
                                    .font(.subheadline.monospacedDigit())
                            }

                            if let md = record.structuredMd, !md.isEmpty {
                                Text(HTMLText.plain(md))
                                    .font(.body)
                                    .textSelection(.enabled)
                            }

                            if let analysis = record.analysis, !analysis.isEmpty {
                                Divider()
                                Text("분석")
                                    .font(.caption.weight(.semibold))
                                    .foregroundStyle(OMP.ink2)
                                Text(HTMLText.plain(analysis))
                                    .font(.subheadline)
                                    .textSelection(.enabled)
                            }
                        }
                        .cardStyle()
                    }
                }

                if let meals = result.meals, !meals.isEmpty {
                    ForEach(meals, id: \.rowID) { meal in
                        VStack(alignment: .leading, spacing: 10) {
                            HStack {
                                Text(mealTypeLabel(meal.mealType))
                                    .font(.caption.weight(.semibold))
                                    .padding(.horizontal, 9)
                                    .padding(.vertical, 5)
                                    .background(OMP.panel, in: RoundedRectangle(cornerRadius: 5, style: .continuous))
                                    .foregroundStyle(.white)
                                Text(meal.date ?? "-")
                                    .font(.subheadline)
                                    .foregroundStyle(OMP.ink2)
                                Spacer()
                                Text(Formatters.kcal(meal.estimatedKcal))
                                    .font(.subheadline.monospacedDigit())
                            }

                            if let items = meal.itemsMd, !items.isEmpty {
                                Text(HTMLText.plain(items))
                                    .font(.body)
                                    .textSelection(.enabled)
                            } else if let structured = meal.structuredMd, !structured.isEmpty {
                                Text(HTMLText.plain(structured))
                                    .font(.body)
                                    .textSelection(.enabled)
                            }

                            macroLine(meal)

                            if let analysis = meal.analysisMd, !analysis.isEmpty {
                                Divider()
                                Text(HTMLText.plain(analysis))
                                    .font(.subheadline)
                                    .textSelection(.enabled)
                            }
                        }
                        .cardStyle()
                    }
                }

                if let inbody = result.inbody {
                    inbodyCard(inbody)
                }
            }
            .padding()
        }
        .background(OMP.concrete)
        .navigationTitle(result.displayTitle)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            if let onDismiss {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("완료", action: onDismiss)
                }
            }
        }
    }

    private var header: some View {
        HStack(spacing: 12) {
            Image(systemName: result.isSuccess ? "checkmark.circle.fill" : "exclamationmark.triangle.fill")
                .font(.system(size: 28))
                .foregroundStyle(result.isSuccess ? OMP.green : OMP.amberText)

            VStack(alignment: .leading, spacing: 4) {
                Text(result.displayMessage)
                    .font(.headline)
                if let confidence = result.confidence {
                    Text(String(format: "신뢰도 %.0f%%", confidence * 100))
                        .font(.caption)
                        .foregroundStyle(OMP.ink2)
                }
            }
            Spacer()
        }
        .cardStyle()
    }

    private func inbodyCard(_ inbody: InbodySnapshot) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("인바디 \(inbody.measuredAt ?? "")", systemImage: "figure.stand")
                .font(.headline)

            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                metric("체중", Formatters.decimal(inbody.weightKg), "kg")
                metric("골격근", Formatters.decimal(inbody.skeletalMuscleKg), "kg")
                metric("체지방", Formatters.decimal(inbody.bodyFatKg), "kg")
                metric("체지방률", Formatters.decimal(inbody.bodyFatPct), "%")
                metric("BMI", Formatters.decimal(inbody.bmi), "")
                metric("BMR", Formatters.decimal(inbody.bmrKcal), "kcal")
            }
        }
        .cardStyle()
    }

    private func metric(_ title: String, _ value: String, _ unit: String) -> some View {
        MetricTile(title: title, value: unit.isEmpty || value == "-" ? value : "\(value)\(unit)")
    }

    @ViewBuilder
    private func macroLine(_ meal: MealRecord) -> some View {
        if meal.proteinG != nil || meal.carbsG != nil || meal.fatG != nil {
            Text("P \(Formatters.grams(meal.proteinG)) · C \(Formatters.grams(meal.carbsG)) · F \(Formatters.grams(meal.fatG))")
                .font(.caption.monospacedDigit())
                .foregroundStyle(OMP.ink2)
        }
    }

    private func mealTypeLabel(_ type: String?) -> String {
        switch (type ?? "").lowercased() {
        case "breakfast": return "아침"
        case "lunch": return "점심"
        case "dinner": return "저녁"
        case "snack": return "간식"
        default: return type ?? "식사"
        }
    }
}

/// Lightweight HTML → plain text for Telegram/coach HTML fragments.
enum HTMLText {
    static func plain(_ html: String) -> String {
        var text = html
        let replacements: [(String, String)] = [
            ("<br>", "\n"), ("<br/>", "\n"), ("<br />", "\n"),
            ("</p>", "\n"), ("</div>", "\n"), ("</li>", "\n"),
            ("<li>", "• "),
        ]
        for (from, to) in replacements {
            text = text.replacingOccurrences(of: from, with: to, options: .caseInsensitive)
        }
        // Strip remaining tags
        while let start = text.range(of: "<"),
              let end = text.range(of: ">", range: start.lowerBound..<text.endIndex) {
            text.removeSubrange(start.lowerBound...end.upperBound)
        }
        return text
            .replacingOccurrences(of: "&nbsp;", with: " ")
            .replacingOccurrences(of: "&lt;", with: "<")
            .replacingOccurrences(of: "&gt;", with: ">")
            .replacingOccurrences(of: "&amp;", with: "&")
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
