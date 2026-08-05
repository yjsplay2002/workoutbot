import SwiftUI

struct TodayView: View {
    let configuration: AppConfiguration
    @StateObject private var viewModel = TodayViewModel()
    @State private var showPhotoUpload = false
    @State private var showTextRecord = false

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
                        QuickActionsCard(
                            onPhoto: { showPhotoUpload = true },
                            onText: { showTextRecord = true }
                        )
                        CaloriesCard(today: summary.today)
                        MacroCard(today: summary.today)
                        CreatineGuideCard()
                        DeficitCard(deficit: summary.deficit, goal: summary.primaryGoal)
                        PlanCard(
                            plan: viewModel.plan,
                            isGenerating: viewModel.isGeneratingPlan,
                            onGenerate: { refresh in
                                Task { await viewModel.generatePlan(configuration: configuration, refresh: refresh) }
                            }
                        )
                        CoachSummaryCard(
                            summary: viewModel.coachSummary,
                            isGenerating: viewModel.isGeneratingSummary,
                            onGenerate: { refresh in
                                Task { await viewModel.generateCoachSummary(configuration: configuration, refresh: refresh) }
                            }
                        )
                        RecentRecordsCard(records: summary.recentRecords)

                        if let action = viewModel.actionMessage {
                            Text(action)
                                .font(.footnote)
                                .foregroundStyle(.secondary)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                    } else if !viewModel.isLoading && viewModel.errorMessage == nil {
                        StateMessageView(title: "데이터 없음", message: "표시할 오늘 데이터가 없습니다.", systemImage: "tray")
                        QuickActionsCard(
                            onPhoto: { showPhotoUpload = true },
                            onText: { showTextRecord = true }
                        )
                    }
                }
                .padding()
            }
            .background(OMP.concrete)
            .navigationTitle("오늘")
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    if viewModel.isLoading || viewModel.isGeneratingPlan || viewModel.isGeneratingSummary {
                        ProgressView()
                    }
                }
                ToolbarItemGroup(placement: .navigationBarLeading) {
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
            .refreshable {
                await viewModel.load(configuration: configuration)
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

// MARK: - Subviews

private struct TodayHeaderView: View {
    let summary: AppSummary

    var body: some View {
        SignBand(showArrow: false) {
            PictoInset(systemImage: "figure.strengthtraining.traditional", size: 46, onYellow: true)
            VStack(alignment: .leading, spacing: 2) {
                Text("\(summary.name)님")
                    .font(.title2.weight(.heavy))
                    .foregroundStyle(OMP.panel)
                Text(summary.date)
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(OMP.yellowInk)
            }
            Spacer(minLength: 0)
        }
    }
}

private struct QuickActionsCard: View {
    let onPhoto: () -> Void
    let onText: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("기록 추가", systemImage: "plus.circle.fill")
                .font(.headline)

            HStack(spacing: 12) {
                ActionButton(title: "사진", systemImage: "camera.fill", tint: OMP.panel, action: onPhoto)
                ActionButton(title: "텍스트", systemImage: "text.badge.plus", tint: OMP.panel, action: onText)
            }
        }
        .cardStyle()
    }
}

private struct ActionButton: View {
    let title: String
    let systemImage: String
    let tint: Color
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(spacing: 8) {
                Image(systemName: systemImage)
                    .font(.title2.weight(.semibold))
                Text(title)
                    .font(.subheadline.weight(.semibold))
            }
            .foregroundStyle(tint)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 16)
            .background(tint.opacity(0.12), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        }
        .buttonStyle(.plain)
    }
}

private struct CaloriesCard: View {
    let today: TodaySummary

    private var progress: Double {
        guard let intake = today.intakeKcal, let target = today.targetKcal, target > 0 else { return 0 }
        return min(max(intake / target, 0), 1)
    }

    private var remaining: Double? {
        guard let intake = today.intakeKcal, let target = today.targetKcal else { return nil }
        return target - intake
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .top, spacing: 12) {
                BoardCell(label: "오늘 섭취", value: Formatters.kcal(today.intakeKcal))
                Rectangle().fill(OMP.panelLine).frame(width: 1, height: 44)
                BoardCell(label: "목표 섭취", value: Formatters.kcal(today.targetKcal))
            }

            if let remaining {
                BoardCell(
                    label: remaining < 0 ? "초과" : "남은 허용",
                    value: Formatters.kcal(abs(remaining)),
                    valueColor: remaining < 0 ? OMP.redOnPanel : OMP.yellow,
                    gate: true
                )
            }

            ProgressView(value: progress)
                .tint(progress >= 1 ? OMP.redOnPanel : OMP.yellow)
                .scaleEffect(x: 1, y: 1.4, anchor: .center)

            HStack(alignment: .top, spacing: 12) {
                BoardCell(label: "운동 소모", value: Formatters.kcal(today.exerciseKcal))
                Rectangle().fill(OMP.panelLine).frame(width: 1, height: 44)
                BoardCell(label: "TDEE", value: Formatters.kcal(today.tdee))
            }
        }
        .boardStyle()
    }
}

private struct MacroCard: View {
    let today: TodaySummary

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Label("매크로 목표", systemImage: "chart.bar.fill")
                .font(.headline)

            MacroRow(name: "단백질", current: today.proteinG, target: today.macros?.proteinG, tint: OMP.panel)
            MacroRow(name: "탄수화물", current: today.carbsG, target: today.macros?.carbsG, tint: OMP.panel)
            MacroRow(name: "지방", current: today.fatG, target: today.macros?.fatG, tint: OMP.panel)
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

private struct CreatineGuideCard: View {
    @State private var isExpanded = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            DisclosureGroup(isExpanded: $isExpanded) {
                VStack(alignment: .leading, spacing: 12) {
                    Text("타이밍보다 **매일 빠짐없이**가 압도적으로 중요 — 근육에 쌓이는 저장형 보충제. 총 6g은 체중 77kg에 적절(5~7g 범위), 3g 분할로 위장 부담 없음. 로딩 없이 약 3~4주면 포화.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)

                    doseRow(order: "1회차 3g", time: "운동 직후 점심 (13시)",
                            reason: "탄수+단백질과 함께 → 인슐린이 근육 흡수 도움")
                    doseRow(order: "2회차 3g", time: "저녁 식사 (19시)",
                            reason: "식사와 함께 = 흡수↑ + 위장 편함 + 까먹지 않음")

                    VStack(alignment: .leading, spacing: 6) {
                        tipLine("비운동일에도 동일하게 6g — 크레아틴에 휴무일 없음")
                        tipLine("물 하루 2L+ (수분을 근육으로 끌어감)")
                        tipLine("카페인과 상쇄 없음 — Hot6 타이밍 겹쳐도 무관")
                        tipLine("먹기 직전에 타서 바로 마시기")
                        tipLine("첫 1~2주 체중 +0.5~1kg은 수분 — 숫자에 흔들리지 말 것")
                    }

                    Text("한 줄: 점심·저녁 식사에 각각 붙이고, 쉬는 날 포함 매일.")
                        .font(.footnote.weight(.bold))
                        .foregroundStyle(OMP.ink)
                }
                .padding(.top, 8)
            } label: {
                Label("크레아틴 3g × 2회 (점심·저녁)", systemImage: "pills.fill")
                    .font(.headline)
                    .foregroundStyle(.primary)
            }
        }
        .cardStyle()
    }

    private func doseRow(order: String, time: String, reason: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 8) {
                Text(order)
                    .font(.subheadline.weight(.bold))
                Text(time)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(OMP.green)
            }
            Text(reason)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(10)
        .background(OMP.inset, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
    }

    private func tipLine(_ text: String) -> some View {
        HStack(alignment: .top, spacing: 6) {
            Text("•")
            Text(text)
        }
        .font(.caption)
        .foregroundStyle(.secondary)
    }
}

private struct DeficitCard: View {
    let deficit: DeficitSummary
    let goal: PrimaryGoal?

    private var achievementColor: Color {
        let pct = deficit.achievementPct ?? 0
        if pct >= 100 { return OMP.green }
        if pct < 80 { return OMP.red }
        return OMP.amberText
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Label("목표 적자", systemImage: "target")
                    .font(.headline)
                Spacer()
                if let daysLeft = deficit.daysLeft {
                    Text("D-\(max(daysLeft, 0))")
                        .font(.subheadline.weight(.heavy).monospacedDigit())
                        .padding(.horizontal, 10)
                        .padding(.vertical, 5)
                        .background(OMP.yellow, in: RoundedRectangle(cornerRadius: 6, style: .continuous))
                        .foregroundStyle(OMP.panel)
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

private struct PlanCard: View {
    let plan: DailyPlanPayload?
    let isGenerating: Bool
    let onGenerate: (Bool) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Label("오늘의 플랜", systemImage: "calendar.badge.clock")
                    .font(.headline)
                Spacer()
                if plan?.cached == true {
                    Text("캐시")
                        .font(.caption2.weight(.bold))
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(.secondary.opacity(0.15), in: Capsule())
                }
            }

            if let plan, plan.isSuccess, plan.error == nil,
               plan.targetKcalIntake != nil || !(plan.breakfastSuggestion ?? "").isEmpty {
                if let intake = plan.targetKcalIntake {
                    Text("권장 섭취 \(Formatters.kcal(intake))")
                        .font(.subheadline.weight(.semibold))
                }
                if let burn = plan.targetKcalBurn {
                    Text("권장 소모 \(Formatters.kcal(burn))")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                mealBlock("아침", plan.breakfastSuggestion)
                mealBlock("점심", plan.lunchSuggestion)
                mealBlock("저녁", plan.dinnerSuggestion)

                if let rationale = plan.rationaleText, !rationale.isEmpty {
                    Text(HTMLText.plain(rationale))
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            } else if let error = plan?.error {
                Text(error)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            } else {
                Text("아직 생성된 플랜이 없습니다. 목표 등록 후 생성해 보세요.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }

            HStack(spacing: 10) {
                Button {
                    onGenerate(false)
                } label: {
                    if isGenerating {
                        ProgressView()
                            .frame(maxWidth: .infinity)
                    } else {
                        Text(plan == nil ? "플랜 생성" : "플랜 불러오기")
                            .frame(maxWidth: .infinity)
                    }
                }
                .buttonStyle(.borderedProminent)
                .disabled(isGenerating)

                if plan != nil {
                    Button("재생성") {
                        onGenerate(true)
                    }
                    .buttonStyle(.bordered)
                    .disabled(isGenerating)
                }
            }
        }
        .cardStyle()
    }

    @ViewBuilder
    private func mealBlock(_ title: String, _ html: String?) -> some View {
        if let html, !html.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(.caption.weight(.bold))
                    .foregroundStyle(.secondary)
                Text(HTMLText.plain(html))
                    .font(.subheadline)
            }
            .padding(.vertical, 2)
        }
    }
}

private struct CoachSummaryCard: View {
    let summary: DailyCoachSummary?
    let isGenerating: Bool
    let onGenerate: (Bool) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Label("오늘 요약", systemImage: "moon.stars.fill")
                .font(.headline)

            if let summary, summary.isSuccess {
                if let md = summary.summaryMd, !md.isEmpty {
                    Text(HTMLText.plain(md))
                        .font(.subheadline)
                        .textSelection(.enabled)
                }
                if let assess = summary.goalAssessmentMd, !assess.isEmpty {
                    Divider()
                    Text("목표 평가")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                    Text(HTMLText.plain(assess))
                        .font(.subheadline)
                        .textSelection(.enabled)
                }
                if (summary.summaryMd ?? "").isEmpty && (summary.goalAssessmentMd ?? "").isEmpty {
                    Text("요약 내용이 비어 있습니다.")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
            } else if let error = summary?.error {
                Text(error)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            } else {
                Text("하루 기록을 바탕으로 코치 요약을 생성할 수 있습니다.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }

            HStack(spacing: 10) {
                Button {
                    onGenerate(false)
                } label: {
                    if isGenerating {
                        ProgressView()
                            .frame(maxWidth: .infinity)
                    } else {
                        Text(summary == nil ? "요약 생성" : "요약 불러오기")
                            .frame(maxWidth: .infinity)
                    }
                }
                .buttonStyle(.borderedProminent)
                .disabled(isGenerating)

                if summary != nil {
                    Button("재생성") {
                        onGenerate(true)
                    }
                    .buttonStyle(.bordered)
                    .disabled(isGenerating)
                }
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
                .foregroundStyle(OMP.ink2)
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
