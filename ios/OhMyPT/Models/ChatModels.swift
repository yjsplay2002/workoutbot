import Foundation

/// One structured confirmation card attached to an assistant message.
/// Every DB write the agent performs is surfaced as a card (trust layer).
struct ChatCard: Codable, Identifiable, Equatable {
    var kind: String
    var refId: Int?
    var title: String
    var rows: [[String]]
    var meta: String?

    var id: String { "\(kind)-\(refId ?? -1)-\(title)" }
}

struct ChatMessage: Codable, Identifiable, Equatable {
    var id: Int
    var role: String
    var content: String
    var cards: [ChatCard]
    var createdAt: String?

    var isUser: Bool { role == "user" }
}

struct ChatSendResponse: Codable {
    var ok: Bool
    var replyMd: String?
    var cards: [ChatCard]?
    var error: String?
}

struct ChatHistoryResponse: Codable {
    var ok: Bool
    var messages: [ChatMessage]
}
