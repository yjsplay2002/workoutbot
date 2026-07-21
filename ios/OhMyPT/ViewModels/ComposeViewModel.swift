import Foundation
import UIKit

@MainActor
final class ComposeViewModel: ObservableObject {
    @Published var caption: String = ""
    @Published var textBody: String = ""
    @Published var selectedImage: UIImage?
    @Published var analyzeText: Bool = false

    @Published private(set) var isSubmitting = false
    @Published var errorMessage: String?
    @Published private(set) var result: AnalysisResult?

    func clearResult() {
        result = nil
        errorMessage = nil
    }

    func upload(configuration: AppConfiguration) async {
        guard configuration.isValid else {
            errorMessage = "설정에서 서버 URL과 user_id를 입력해 주세요."
            return
        }
        guard let image = selectedImage else {
            errorMessage = "사진을 먼저 선택해 주세요."
            return
        }

        isSubmitting = true
        errorMessage = nil
        result = nil
        defer { isSubmitting = false }

        do {
            result = try await APIClient(configuration: configuration)
                .uploadPhoto(image: image, caption: caption.trimmingCharacters(in: .whitespacesAndNewlines))
        } catch {
            errorMessage = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }

    func submitText(configuration: AppConfiguration) async {
        guard configuration.isValid else {
            errorMessage = "설정에서 서버 URL과 user_id를 입력해 주세요."
            return
        }
        let text = textBody.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else {
            errorMessage = "기록할 내용을 입력해 주세요."
            return
        }

        isSubmitting = true
        errorMessage = nil
        result = nil
        defer { isSubmitting = false }

        do {
            result = try await APIClient(configuration: configuration)
                .submitTextRecord(text: text, analyze: analyzeText)
        } catch {
            errorMessage = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }
}
