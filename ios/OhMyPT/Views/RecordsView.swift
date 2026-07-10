import SwiftUI

struct RecordsView: View {
    let configuration: AppConfiguration
    @StateObject private var viewModel = RecordsViewModel()
    @State private var selectedRecord: WorkoutRecord?

    var body: some View {
        NavigationStack {
            Group {
                if viewModel.isLoading && viewModel.records.isEmpty {
                    LoadingView(message: "운동 기록을 불러오는 중")
                } else if let errorMessage = viewModel.errorMessage {
                    StateMessageView(title: "불러오기 실패", message: errorMessage, systemImage: "wifi.exclamationmark")
                        .padding()
                } else if viewModel.records.isEmpty {
                    StateMessageView(title: "기록 없음", message: "최근 운동 기록이 없습니다.", systemImage: "tray")
                        .padding()
                } else {
                    List(viewModel.records) { record in
                        Button {
                            selectedRecord = record
                        } label: {
                            RecordRow(record: record)
                        }
                        .buttonStyle(.plain)
                    }
                    .listStyle(.insetGrouped)
                    .refreshable {
                        await viewModel.load(configuration: configuration)
                    }
                }
            }
            .navigationTitle("운동 기록")
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
            .sheet(item: $selectedRecord) { record in
                RecordDetailView(record: record)
            }
        }
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
                        .background(.blue.opacity(0.12), in: Capsule())
                        .foregroundStyle(.blue)

                    Text(record.date ?? "-")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }

                if let createdAt = record.createdAt, !createdAt.isEmpty {
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
}
