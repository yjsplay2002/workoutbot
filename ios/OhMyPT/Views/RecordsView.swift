import Charts
import SwiftUI

struct RecordsView: View {
    enum Segment: String, CaseIterable {
        case workouts = "운동"
        case meals = "식단"
    }

    let configuration: AppConfiguration
    @StateObject private var viewModel = RecordsViewModel()
    @State private var segment: Segment = .workouts
    @State private var selectedRecord: WorkoutRecord?
    @State private var showPhotoUpload = false
    @State private var showTextRecord = false

    private var mealDays: [(date: String, meals: [MealEntry], totalKcal: Double, totalProtein: Double)] {
        let grouped = Dictionary(grouping: viewModel.meals) { $0.date ?? "-" }
        return grouped.keys.sorted(by: >).map { date in
            let dayMeals = grouped[date] ?? []
            return (
                date: date,
                meals: dayMeals,
                totalKcal: dayMeals.compactMap(\.estimatedKcal).reduce(0, +),
                totalProtein: dayMeals.compactMap(\.proteinG).reduce(0, +)
            )
        }
    }

    var body: some View {
        NavigationStack {
            Group {
                if viewModel.isLoading && viewModel.records.isEmpty {
                    LoadingView(message: "운동 기록을 불러오는 중")
                } else if let errorMessage = viewModel.errorMessage {
                    StateMessageView(title: "불러오기 실패", message: errorMessage, systemImage: "wifi.exclamationmark")
                        .padding()
                } else {
                    List {
                        Section {
                            Picker("종류", selection: $segment) {
                                ForEach(Segment.allCases, id: \.self) { seg in
                                    Text(seg.rawValue).tag(seg)
                                }
                            }
                            .pickerStyle(.segmented)
                            .listRowInsets(EdgeInsets(top: 4, leading: 16, bottom: 4, trailing: 16))
                            .listRowBackground(Color.clear)
                        }

                        if segment == .workouts {
                            Section {
                                WeeklyStatsCard(
                                    stats: viewModel.weeklyStats,
                                    totalKcal: viewModel.weekWorkoutKcal,
                                    sessionCount: viewModel.weekSessionCount
                                )
                                .listRowInsets(EdgeInsets(top: 8, leading: 16, bottom: 8, trailing: 16))
                                .listRowBackground(Color.clear)
                            }

                            Section {
                                if viewModel.records.isEmpty {
                                    StateMessageView(
                                        title: "기록 없음",
                                        message: "사진이나 텍스트로 첫 운동을 남겨 보세요.",
                                        systemImage: "tray"
                                    )
                                    .listRowBackground(Color.clear)
                                } else {
                                    ForEach(viewModel.records) { record in
                                        Button {
                                            selectedRecord = record
                                        } label: {
                                            RecordRow(record: record)
                                        }
                                        .buttonStyle(.plain)
                                    }
                                }
                            } header: {
                                Text("최근 기록")
                            }
                        } else {
                            if viewModel.meals.isEmpty {
                                Section {
                                    StateMessageView(
                                        title: "식단 기록 없음",
                                        message: "코치 탭에서 “닭가슴살 샐러드 먹었어”라고 말하거나 사진을 보내면 저장됩니다.",
                                        systemImage: "fork.knife"
                                    )
                                    .listRowBackground(Color.clear)
                                }
                            } else {
                                ForEach(mealDays, id: \.date) { day in
                                    Section {
                                        ForEach(day.meals) { meal in
                                            MealRow(meal: meal)
                                        }
                                    } header: {
                                        HStack {
                                            Text(day.date)
                                            Spacer()
                                            Text("\(Formatters.kcal(day.totalKcal)) · 단백질 \(Formatters.grams(day.totalProtein))")
                                                .monospacedDigit()
                                        }
                                    }
                                }
                            }
                        }
                    }
                    .listStyle(.insetGrouped)
                    .scrollContentBackground(.hidden)
                    .background(OMP.concrete)
                    .refreshable {
                        await viewModel.load(configuration: configuration)
                    }
                }
            }
            .navigationTitle("기록")
            .toolbar {
                ToolbarItemGroup(placement: .navigationBarTrailing) {
                    if viewModel.isLoading {
                        ProgressView()
                    }
                    Button {
                        showPhotoUpload = true
                    } label: {
                        Image(systemName: "camera.fill")
                    }
                    Button {
                        showTextRecord = true
                    } label: {
                        Image(systemName: "square.and.pencil")
                    }
                }
            }
            .task(id: configuration) {
                await viewModel.load(configuration: configuration)
            }
            .sheet(item: $selectedRecord) { record in
                RecordDetailView(record: record)
            }
            .sheet(isPresented: $showPhotoUpload, onDismiss: {
                Task { await viewModel.load(configuration: configuration) }
            }) {
                NavigationStack {
                    PhotoUploadView(configuration: configuration)
                }
            }
            .sheet(isPresented: $showTextRecord, onDismiss: {
                Task { await viewModel.load(configuration: configuration) }
            }) {
                NavigationStack {
                    TextRecordView(configuration: configuration)
                }
            }
        }
    }
}

// MARK: - Weekly chart

private struct WeeklyStatsCard: View {
    let stats: [DayStat]
    let totalKcal: Double
    let sessionCount: Int

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Label("이번 주 운동", systemImage: "chart.bar.fill")
                    .font(.headline)
                Spacer()
            }

            HStack(spacing: 12) {
                MetricPill(
                    title: "소모 합계",
                    value: Formatters.kcal(totalKcal),
                    systemImage: "flame.fill",
                    tint: OMP.ink
                )
                MetricPill(
                    title: "세션",
                    value: "\(sessionCount)회",
                    systemImage: "figure.run",
                    tint: OMP.ink
                )
            }

            if stats.contains(where: { $0.workoutKcal > 0 || $0.sessionCount > 0 }) {
                Chart(stats) { day in
                    BarMark(
                        x: .value("요일", day.label),
                        y: .value("kcal", day.workoutKcal)
                    )
                    .foregroundStyle(OMP.ink)
                }
                .chartYAxis {
                    AxisMarks(position: .leading) { value in
                        AxisGridLine()
                        AxisValueLabel {
                            if let v = value.as(Double.self) {
                                Text("\(Int(v))")
                                    .font(.caption2)
                            }
                        }
                    }
                }
                .frame(height: 160)
                .padding(.top, 4)
            } else {
                Text("최근 7일 운동 데이터가 없습니다.")
                    .font(.subheadline)
                    .foregroundStyle(OMP.ink2)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.vertical, 8)
            }
        }
        .cardStyle()
    }
}

private struct RecordRow: View {
    let record: WorkoutRecord

    var body: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Text(record.category ?? "운동")
                        .font(.caption.weight(.bold))
                        .padding(.horizontal, 9)
                        .padding(.vertical, 5)
                        .background(OMP.panel, in: RoundedRectangle(cornerRadius: 5, style: .continuous))
                        .foregroundStyle(.white)

                    Text(record.date ?? "-")
                        .font(.subheadline)
                        .foregroundStyle(OMP.ink2)
                }

                if let preview = record.structuredMd?.trimmingCharacters(in: .whitespacesAndNewlines),
                   !preview.isEmpty {
                    Text(HTMLText.plain(preview))
                        .font(.caption)
                        .foregroundStyle(OMP.ink2)
                        .lineLimit(2)
                } else if let createdAt = record.createdAt, !createdAt.isEmpty {
                    Text(createdAt)
                        .font(.caption)
                        .foregroundStyle(OMP.ink2.opacity(0.7))
                }
            }

            Spacer()

            VStack(alignment: .trailing, spacing: 4) {
                Text(Formatters.kcal(record.estimatedKcal))
                    .font(.headline.monospacedDigit())
                Image(systemName: "chevron.right")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(OMP.ink2.opacity(0.7))
            }
        }
        .contentShape(Rectangle())
        .padding(.vertical, 4)
    }

}

private struct MealRow: View {
    let meal: MealEntry

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Text(meal.mealTypeLabel)
                .font(.caption.weight(.bold))
                .padding(.horizontal, 9)
                .padding(.vertical, 5)
                .background(OMP.panel, in: RoundedRectangle(cornerRadius: 5, style: .continuous))
                .foregroundStyle(.white)
                .frame(width: 52)

            VStack(alignment: .leading, spacing: 4) {
                if let md = meal.structuredMd?.trimmingCharacters(in: .whitespacesAndNewlines), !md.isEmpty {
                    Text(HTMLText.plain(md))
                        .font(.subheadline)
                        .lineLimit(3)
                } else {
                    Text("내용 없음")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
                if meal.proteinG != nil || meal.carbsG != nil || meal.fatG != nil {
                    Text("단백질 \(Formatters.grams(meal.proteinG)) · 탄수 \(Formatters.grams(meal.carbsG)) · 지방 \(Formatters.grams(meal.fatG))")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .monospacedDigit()
                }
            }

            Spacer(minLength: 8)

            Text(Formatters.kcal(meal.estimatedKcal))
                .font(.subheadline.weight(.heavy).monospacedDigit())
        }
        .padding(.vertical, 4)
    }
}
