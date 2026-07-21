import SwiftUI

struct TextRecordView: View {
    let configuration: AppConfiguration
    @StateObject private var viewModel = ComposeViewModel()
    @Environment(\.dismiss) private var dismiss
    @State private var showResult = false

    var body: some View {
        Form {
            Section("기록 내용") {
                TextField(
                    "예: 스쿼트 100kg 5x5 / 점심 닭가슴살 200g + 현미밥",
                    text: $viewModel.textBody,
                    axis: .vertical
                )
                .lineLimit(6...14)
            }

            Section {
                Toggle("운동이면 코치 분석도 생성", isOn: $viewModel.analyzeText)
            } footer: {
                Text("운동으로 분류되면 구조화 저장 후, 옵션 켜면 코치 분석까지 생성합니다. 식단은 항상 칼로리·매크로 분석이 포함됩니다.")
            }

            if let error = viewModel.errorMessage {
                Section {
                    Text(error)
                        .foregroundStyle(.red)
                        .font(.subheadline)
                }
            }

            Section {
                Button {
                    Task {
                        await viewModel.submitText(configuration: configuration)
                        if viewModel.result != nil {
                            showResult = true
                        }
                    }
                } label: {
                    HStack {
                        Spacer()
                        if viewModel.isSubmitting {
                            ProgressView()
                                .padding(.trailing, 8)
                            Text("분석·저장 중…")
                        } else {
                            Label("기록 저장", systemImage: "square.and.pencil")
                        }
                        Spacer()
                    }
                }
                .disabled(
                    viewModel.textBody.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                        || viewModel.isSubmitting
                )
            }
        }
        .navigationTitle("텍스트 기록")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .navigationBarLeading) {
                Button("닫기") { dismiss() }
            }
        }
        .sheet(isPresented: $showResult) {
            if let result = viewModel.result {
                NavigationStack {
                    AnalysisResultView(result: result) {
                        showResult = false
                        dismiss()
                    }
                }
            }
        }
    }
}
