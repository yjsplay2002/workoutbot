import Foundation
import UIKit

enum APIError: LocalizedError {
    case invalidBaseURL
    case invalidUserID
    case invalidResponse
    case emptyData
    case httpStatus(Int, String?)
    case decoding(Error)
    case transport(Error)
    case imageEncoding

    var errorDescription: String? {
        switch self {
        case .invalidBaseURL:
            return "서버 URL이 올바르지 않습니다."
        case .invalidUserID:
            return "텔레그램 user_id를 숫자로 입력해 주세요."
        case .invalidResponse:
            return "서버 응답을 읽을 수 없습니다."
        case .emptyData:
            return "서버 응답이 비어 있습니다."
        case .httpStatus(let code, let message):
            if let message, !message.isEmpty {
                return "서버 오류 \(code): \(message)"
            }
            return "서버 오류 \(code)가 발생했습니다."
        case .decoding:
            return "서버 응답 형식이 예상과 다릅니다."
        case .transport(let error):
            return error.localizedDescription
        case .imageEncoding:
            return "이미지를 준비하지 못했습니다."
        }
    }
}

struct APIClient {
    private let configuration: AppConfiguration
    private let session: URLSession
    private let decoder: JSONDecoder

    init(configuration: AppConfiguration, session: URLSession = .shared) {
        self.configuration = configuration
        self.session = session
        self.decoder = JSONDecoder()
        self.decoder.keyDecodingStrategy = .convertFromSnakeCase
    }

    // MARK: - Read

    func fetchSummary() async throws -> AppSummary {
        let url = try makeURL(path: "api/app/summary", queryItems: [
            URLQueryItem(name: "user_id", value: String(try requireUserID()))
        ])
        return try await request(url)
    }

    func fetchRecords(limit: Int = 50) async throws -> [WorkoutRecord] {
        let url = try makeURL(path: "api/records", queryItems: [
            URLQueryItem(name: "user_id", value: String(try requireUserID())),
            URLQueryItem(name: "limit", value: String(limit))
        ])
        return try await request(url)
    }

    func fetchMeals(limit: Int = 60) async throws -> [MealEntry] {
        let url = try makeURL(path: "api/app/meals", queryItems: [
            URLQueryItem(name: "user_id", value: String(try requireUserID())),
            URLQueryItem(name: "limit", value: String(limit))
        ])
        return try await request(url)
    }

    // MARK: - Write

    func uploadPhoto(image: UIImage, caption: String) async throws -> AnalysisResult {
        let userID = try requireUserID()
        guard let jpeg = image.jpegData(compressionQuality: 0.82) else {
            throw APIError.imageEncoding
        }

        let url = try makeURL(path: "api/app/upload", queryItems: [])
        let boundary = "Boundary-\(UUID().uuidString)"
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        applyToken(to: &request)

        var body = Data()
        appendFormField(to: &body, boundary: boundary, name: "user_id", value: String(userID))
        appendFormField(to: &body, boundary: boundary, name: "caption", value: caption)
        appendFileField(
            to: &body,
            boundary: boundary,
            name: "photo",
            filename: "photo.jpg",
            mimeType: "image/jpeg",
            data: jpeg
        )
        body.append("--\(boundary)--\r\n".data(using: .utf8)!)
        request.httpBody = body

        return try await send(request)
    }

    func submitTextRecord(text: String, analyze: Bool = false) async throws -> AnalysisResult {
        let url = try makeURL(path: "api/app/record", queryItems: [])
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        applyToken(to: &request)

        let payload: [String: Any] = [
            "user_id": try requireUserID(),
            "text": text,
            "analyze": analyze
        ]
        request.httpBody = try JSONSerialization.data(withJSONObject: payload)
        return try await send(request)
    }

    func generatePlan(refresh: Bool = false) async throws -> DailyPlanPayload {
        let url = try makeURL(path: "api/app/plan", queryItems: [])
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        applyToken(to: &request)

        let payload: [String: Any] = [
            "user_id": try requireUserID(),
            "refresh": refresh
        ]
        request.httpBody = try JSONSerialization.data(withJSONObject: payload)
        return try await send(request)
    }

    func generateDailySummary(refresh: Bool = false) async throws -> DailyCoachSummary {
        let url = try makeURL(path: "api/app/daily-summary", queryItems: [])
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        applyToken(to: &request)

        let payload: [String: Any] = [
            "user_id": try requireUserID(),
            "refresh": refresh
        ]
        request.httpBody = try JSONSerialization.data(withJSONObject: payload)
        return try await send(request)
    }

    // MARK: - v2 Agent Chat

    func fetchChatHistory(limit: Int = 60) async throws -> [ChatMessage] {
        let url = try makeURL(path: "api/v2/chat/history", queryItems: [
            URLQueryItem(name: "user_id", value: String(try requireUserID())),
            URLQueryItem(name: "limit", value: String(limit))
        ])
        let response: ChatHistoryResponse = try await request(url)
        return response.messages
    }

    func sendChatText(_ text: String) async throws -> ChatSendResponse {
        let url = try makeURL(path: "api/v2/chat", queryItems: [])
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        applyToken(to: &request)

        let payload: [String: Any] = [
            "user_id": try requireUserID(),
            "text": text
        ]
        request.httpBody = try JSONSerialization.data(withJSONObject: payload)
        return try await send(request)
    }

    func sendChatPhoto(image: UIImage, text: String) async throws -> ChatSendResponse {
        let userID = try requireUserID()
        guard let jpeg = image.jpegData(compressionQuality: 0.82) else {
            throw APIError.imageEncoding
        }

        let url = try makeURL(path: "api/v2/chat", queryItems: [])
        let boundary = "Boundary-\(UUID().uuidString)"
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        applyToken(to: &request)

        var body = Data()
        appendFormField(to: &body, boundary: boundary, name: "user_id", value: String(userID))
        appendFormField(to: &body, boundary: boundary, name: "text", value: text)
        appendFileField(
            to: &body,
            boundary: boundary,
            name: "photo",
            filename: "photo.jpg",
            mimeType: "image/jpeg",
            data: jpeg
        )
        body.append("--\(boundary)--\r\n".data(using: .utf8)!)
        request.httpBody = body

        return try await send(request)
    }

    // MARK: - Internals

    private func requireUserID() throws -> Int {
        guard let userID = configuration.userID else {
            throw APIError.invalidUserID
        }
        return userID
    }

    private func makeURL(path: String, queryItems: [URLQueryItem]) throws -> URL {
        let trimmed = configuration.normalizedBaseURL.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        guard let baseURL = URL(string: trimmed), let scheme = baseURL.scheme, !scheme.isEmpty else {
            throw APIError.invalidBaseURL
        }

        let fullURL = path
            .split(separator: "/")
            .reduce(baseURL) { partialURL, component in
                partialURL.appendingPathComponent(String(component))
            }
        guard var components = URLComponents(url: fullURL, resolvingAgainstBaseURL: false) else {
            throw APIError.invalidBaseURL
        }
        if !queryItems.isEmpty {
            components.queryItems = queryItems
        }

        guard let url = components.url else {
            throw APIError.invalidBaseURL
        }
        return url
    }

    private func applyToken(to request: inout URLRequest) {
        let token = configuration.trimmedToken
        if !token.isEmpty {
            request.setValue(token, forHTTPHeaderField: "X-App-Token")
        }
    }

    private func request<T: Decodable>(_ url: URL) async throws -> T {
        var request = URLRequest(url: url)
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        applyToken(to: &request)
        return try await send(request)
    }

    private func send<T: Decodable>(_ request: URLRequest) async throws -> T {
        do {
            let (data, response) = try await session.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse else {
                throw APIError.invalidResponse
            }

            // 422 is used for "classified but failed extraction" — still decode body.
            let acceptable = (200..<300).contains(httpResponse.statusCode) || httpResponse.statusCode == 422
            guard acceptable else {
                throw APIError.httpStatus(httpResponse.statusCode, parseErrorMessage(from: data))
            }

            guard !data.isEmpty else {
                throw APIError.emptyData
            }

            do {
                return try decoder.decode(T.self, from: data)
            } catch {
                throw APIError.decoding(error)
            }
        } catch let error as APIError {
            throw error
        } catch {
            throw APIError.transport(error)
        }
    }

    private func parseErrorMessage(from data: Data) -> String? {
        guard !data.isEmpty else { return nil }

        if
            let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
            let message = object["error"] as? String ?? object["detail"] as? String
        {
            return message
        }

        return String(data: data, encoding: .utf8)
    }

    private func appendFormField(to body: inout Data, boundary: String, name: String, value: String) {
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"\(name)\"\r\n\r\n".data(using: .utf8)!)
        body.append("\(value)\r\n".data(using: .utf8)!)
    }

    private func appendFileField(
        to body: inout Data,
        boundary: String,
        name: String,
        filename: String,
        mimeType: String,
        data: Data
    ) {
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append(
            "Content-Disposition: form-data; name=\"\(name)\"; filename=\"\(filename)\"\r\n".data(using: .utf8)!
        )
        body.append("Content-Type: \(mimeType)\r\n\r\n".data(using: .utf8)!)
        body.append(data)
        body.append("\r\n".data(using: .utf8)!)
    }
}
