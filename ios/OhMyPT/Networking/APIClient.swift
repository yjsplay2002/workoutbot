import Foundation

enum APIError: LocalizedError {
    case invalidBaseURL
    case invalidUserID
    case invalidResponse
    case emptyData
    case httpStatus(Int, String?)
    case decoding(Error)
    case transport(Error)

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

    func fetchSummary() async throws -> AppSummary {
        let url = try makeURL(path: "api/app/summary", queryItems: [
            URLQueryItem(name: "user_id", value: String(try requireUserID()))
        ])
        return try await request(url)
    }

    func fetchRecords(limit: Int = 20) async throws -> [WorkoutRecord] {
        let url = try makeURL(path: "api/records", queryItems: [
            URLQueryItem(name: "user_id", value: String(try requireUserID())),
            URLQueryItem(name: "limit", value: String(limit))
        ])
        return try await request(url)
    }

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
        components.queryItems = queryItems

        guard let url = components.url else {
            throw APIError.invalidBaseURL
        }
        return url
    }

    private func request<T: Decodable>(_ url: URL) async throws -> T {
        var request = URLRequest(url: url)
        request.setValue("application/json", forHTTPHeaderField: "Accept")

        let token = configuration.trimmedToken
        if !token.isEmpty {
            request.setValue(token, forHTTPHeaderField: "X-App-Token")
        }

        do {
            let (data, response) = try await session.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse else {
                throw APIError.invalidResponse
            }

            guard (200..<300).contains(httpResponse.statusCode) else {
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
}
