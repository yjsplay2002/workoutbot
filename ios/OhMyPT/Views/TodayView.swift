import SwiftUI

struct TodayView: View {
    let configuration: AppConfiguration
    @StateObject private var viewModel = TodayViewModel()

    var body: some View {
        NavigationStack {
            ScrollView {
                LazyVStack(spacing: 16) {
                    if viewModel.isLoading && viewModel.summary == nil {
                        LoadingView(message: "오늘 데이터를 불러오는 중")
                    } else if let errorMessage = viewModel.errorMessage {
                        StateMessageView(title: "불러오기 실패", message: errorMessage, systemImage: "wifi.exclamationmark")
                    }

                    if let summary = viewModel.summary {
                        TodayHeaderView(summary: summary)
                        CaloriesCard(today: summary.today)
                        MacroCard(today: summary.today)
                        DeficitCard(deficit: summary.deficit, goal: summary.primaryGoal)
                        RecentRecordsCard(records: summary.recentRecords)
                    } else if !viewModel.isLoading && viewModel.errorMessage == nil {
                        StateMessageView(title: "데이터 없음", message: "표시할 오늘 데이터가 없습니다.", systemImage: "tray")
                    }
                }
                .padding()
            }
            .background(Color(.systemGroupedBackground))
            .navigationTitle("오늘")
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    if viewModel.isLoading {
                        ProgressView()
                    }
                }
            }
            .task(id: configuration) {
                await viewModel.load(configuration: configuration)
            }
            .refreshable {
                await viewModel.load(configuration: configuration)
            }
        }
    }
}

private struct TodayHeaderView: View {
    let summary: AppSummary

    var body: some View {
        HStack(alignment: .center, spacing: 12) {
            Image(systemName: "figure.strengthtraining.traditional")
                .font(.system(size: 34, weight: .semibold))
                .foregroundStyle(.white)
                .frame(width: 58, height: 58)
                .background(.blue.gradient, in: RoundedRectangle(cornerRadius: 16, style: .continuous))

            VStack(alignment: .leading, spacing: 4) {
                Text("\(summary.name)님")
                    .font(.title2.weight(.bold))
                Text(summary.date)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }

            Spacer()
        }
        .cardStyle()
    }
}

private struct CaloriesCard: View {
    let today: TodaySummary

    private var progress: Double {
        guard let intake = today.intakeKcal, let target = today.targetKcal, target > 0 else { return 0 }
        return min(max(intake / target, 0), 1)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Label("오늘 칼로리", systemImage: "flame.fill")
                .font(.headline)
                .foregroundStyle(.primary)

            VStack(alignment: .leading, spacing: 8) {
                HStack(alignment: .firstTextBaseline) {
                    Text(Formatters.kcal(today.intakeKcal))
                        .font(.system(.largeTitle, design: .rounded, weight: .bold))
                    Text("/ \(Formatters.kcal(today.targetKcal))")
                        .font(.headline)
                        .foregroundStyle(.secondary)
                    Spacer()
                }

                ProgressView(value: progress)
                    .tint(progress >= 1 ? .green : .blue)
                    .scaleEffect(x: 1, y: 1.4, anchor: .center)
            }

            HStack(spacing: 12) {
                MetricPill(title: "운동 소모", value: Formatters.kcal(today.exerciseKcal), systemImage: "bolt.heart.fill", tint: .orange)
                MetricPill(title: "TDEE", value: Formatters.kcal(today.tdee), systemImage: "speedometer", tint: .purple)
            }
        }
        .cardStyle()
    }
}

private struct MacroCard: View {
    let today: TodaySummary

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Label("매크로 목표", systemImage: "chart.bar.fill")
                .font(.headline)

            MacroRow(name: "단백질", current: today.proteinG, target: today.macros?.proteinG, tint: .red)
            MacroRow(name: "탄수화물", current: today.carbsG, target: today.macros?.carbsG, tint: .green)
            MacroRow(name: "지방", current: today.fatG, target: today.macros?.fatG, tint: .yellow)
        }
        .cardStyle()
    }
}

private struct MacroRow: View {
    let name: String
    let current: Double?
    let target: Double?
    let tint: Color

    private var progress: Double {
        guard let current, let target, target > 0 else { return 0 }
        return min(max(current / target, 0), 1)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(name)
                    .font(.subheadline.weight(.semibold))
                Spacer()
                Text("\(Formatters.grams(current)) / \(Formatters.grams(target))")
                    .font(.subheadline.monospacedDigit())
                    .foregroundStyle(.secondary)
            }

            ProgressView(value: progress)
                .tint(tint)
        }
    }
}

private struct DeficitCard: View {
    let deficit: DeficitSummary
    let goal: PrimaryGoal?

    private var achievementColor: Color {
        let pct = deficit.achievementPct ?? 0
        if pct >= 100 { return .green }
        if pct < 80 { return .red }
        return .orange
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Label("목표 적자", systemImage: "target")
                    .font(.headline)
                Spacer()
                if let daysLeft = deficit.daysLeft {
                    Text("D-\(max(daysLeft, 0))")
                        .font(.caption.weight(.bold))
                        .padding(.horizontal, 10)
                        .padding(.vertical, 5)
                        .background(.blue.opacity(0.14), in: Capsule())
                        .foregroundStyle(.blue)
                }
            }

            if deficit.available {
                if let goal {
                    GoalLine(goal: goal, deficit: deficit)
                }

                LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
                    MetricTile(title: "필요 총 적자", value: Formatters.kcal(deficit.totalNeeded))
                    MetricTile(title: "하루 필요 적자", value: Formatters.kcal(deficit.dailyTarget))
                    MetricTile(title: "실제 달성", value: Formatters.kcal(deficit.actualCumulative))
                    MetricTile(title: "달성률", value: Formatters.percent(deficit.achievementPct), valueColor: achievementColor)
                }
            } else {
                StateMessageView(title: "목표 정보 없음", message: deficit.reason ?? "목표 적자를 계산할 수 없습니다.", systemImage: "info.circle")
                    .padding(.vertical, 4)
            }
        }
        .cardStyle()
    }
}

private struct RecentRecordsCard: View {
    let records: [WorkoutRecord]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("최근 운동", systemImage: "clock.arrow.circlepath")
                .font(.headline)

            if records.isEmpty {
                Text("최근 운동 기록이 없습니다.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
            } else {
                ForEach(records.prefix(5)) { record in
                    HStack {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(record.category ?? "운동")
                                .font(.subheadline.weight(.semibold))
                            Text(record.date ?? "-")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }

                        Spacer()

                        Text(Formatters.kcal(record.estimatedKcal))
                            .font(.subheadline.monospacedDigit())
                            .foregroundStyle(.secondary)
                    }
                    .padding(.vertical, 4)
                }
            }
        }
        .cardStyle()
    }
}

private struct GoalLine: View {
    let goal: PrimaryGoal
    let deficit: DeficitSummary

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "flag.checkered")
                .foregroundStyle(.blue)
            Text("\(deficit.label ?? goal.metric) 목표 \(Formatters.decimal(goal.targetValue))\(deficit.unit ?? "")")
                .font(.subheadline)
                .foregroundStyle(.secondary)
            Spacer()
            if let targetDate = goal.targetDate {
                Text(targetDate)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }
}
