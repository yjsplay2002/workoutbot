import SwiftUI
import UIKit

@MainActor
final class ChatViewModel: ObservableObject {
    @Published var messages: [ChatMessage] = []
    @Published var draft: String = ""
    @Published var pendingImage: UIImage?
    @Published var isSending = false
    @Published var isLoadingHistory = false
    @Published var errorMessage: String?

    private let client: APIClient
    private var localID = -1

    init(configuration: AppConfiguration) {
        self.client = APIClient(configuration: configuration)
    }

    func loadHistory() async {
        guard messages.isEmpty else { return }
        isLoadingHistory = true
        defer { isLoadingHistory = false }
        do {
            messages = try await client.fetchChatHistory()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func send() async {
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        let image = pendingImage
        guard !text.isEmpty || image != nil else { return }
        guard !isSending else { return }

        draft = ""
        pendingImage = nil
        errorMessage = nil
        isSending = true
        defer { isSending = false }

        appendLocal(role: "user", content: text.isEmpty ? "[사진]" : text)

        do {
            let response: ChatSendResponse
            if let image {
                response = try await client.sendChatPhoto(image: image, text: text)
            } else {
                response = try await client.sendChatText(text)
            }
            let reply = response.replyMd ?? response.error ?? "응답이 비어 있어요."
            appendLocal(role: "assistant", content: reply, cards: response.cards ?? [])
        } catch {
            appendLocal(role: "assistant", content: "전송에 실패했어요. \(error.localizedDescription)")
        }
    }

    private func appendLocal(role: String, content: String, cards: [ChatCard] = []) {
        messages.append(ChatMessage(id: localID, role: role, content: content, cards: cards, createdAt: nil))
        localID -= 1
    }
}
