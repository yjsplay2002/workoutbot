import SwiftUI

struct RecordDetailView: View {
    let record: WorkoutRecord
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    VStack(alignment: .leading, spacing: 10) {
                        HStack {
                            Text(record.category ?? "운동")
                                .font(.caption.weight(.bold))
                                .padding(.horizontal, 10)
                                .padding(.vertical, 6)
                                .background(OMP.panel, in: RoundedRectangle(cornerRadius: 5, style: .continuous))
                                .foregroundStyle(.white)

                            Spacer()

                            Text(Formatters.kcal(record.estimatedKcal))
                                .font(.headline.monospacedDigit())
                        }

                        Text(record.date ?? "-")
                            .font(.title3.weight(.semibold))
                    }
                    .cardStyle()

                    DetailSection(title: "운동 내용", systemImage: "doc.text", text: record.structuredMd)
                    DetailSection(title: "분석", systemImage: "sparkles", text: record.analysis)
                }
                .padding()
            }
            .background(OMP.concrete)
            .navigationTitle("기록 상세")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("닫기") {
                        dismiss()
                    }
                }
            }
        }
    }
}

private struct DetailSection: View {
    let title: String
    let systemImage: String
    let text: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label(title, systemImage: systemImage)
                .font(.headline)

            if let text, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                Text(HTMLText.plain(text))
                    .font(.body)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .textSelection(.enabled)
            } else {
                Text("내용이 없습니다.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
        }
        .cardStyle()
    }
}
