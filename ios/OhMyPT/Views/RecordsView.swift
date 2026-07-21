import Charts
import SwiftUI

struct RecordsView: View {
    let configuration: AppConfiguration
    @StateObject private var viewModel = RecordsViewModel()
    @State private var selectedRecord: WorkoutRecord?
    @State private var showPhotoUpload = false
    @State private var showTextRecord = false

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
                    }
                    .listStyle(.insetGrouped)
                    .refreshable {
                        await viewModel.load(configuration: configuration)
                    }
                }
            }
            .navigationTitle("운동 기록")
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
                    tint: .orange
                )
                MetricPill(
                    title: "세션",
                    value: "\(sessionCount)회",
                    systemImage: "figure.run",
                    tint: .blue
                )
            }

            if stats.contains(where: { $0.workoutKcal > 0 || $0.sessionCount > 0 }) {
                Chart(stats) { day in
                    BarMark(
                        x: .value("요일", day.label),
                        y: .value("kcal", day.workoutKcal)
                    )
                    .foregroundStyle(Color.blue.gradient)
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
                    .foregroundStyle(.secondary)
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
                        .font(.caption.weight(.semibold))
                        .padding(.horizontal, 9)
                        .padding(.vertical, 5)
                        .background(categoryColor(record.category).opacity(0.12), in: Capsule())
                        .foregroundStyle(categoryColor(record.category))

                    Text(record.date ?? "-")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }

                if let preview = record.structuredMd?.trimmingCharacters(in: .whitespacesAndNewlines),
                   !preview.isEmpty {
                    Text(HTMLText.plain(preview))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                } else if let createdAt = record.createdAt, !createdAt.isEmpty {
                    Text(createdAt)
                        .font(.caption)
                        .foregroundStyle(.tertiary)
                }
            }

            Spacer()

            VStack(alignment: .trailing, spacing: 4) {
                Text(Formatters.kcal(record.estimatedKcal))
                    .font(.headline.monospacedDigit())
                Image(systemName: "chevron.right")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.tertiary)
            }
        }
        .contentShape(Rectangle())
        .padding(.vertical, 4)
    }

    private func categoryColor(_ category: String?) -> Color {
        switch (category ?? "").lowercased() {
        case "chest", "가슴": return .red
        case "back", "등": return .blue
        case "legs", "하체", "다리": return .green
        case "shoulders", "어깨": return .orange
        case "arms", "팔": return .purple
        case "cardio", "유산소": return .pink
        default: return .blue
        }
    }
}
