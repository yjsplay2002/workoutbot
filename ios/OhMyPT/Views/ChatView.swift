import PhotosUI
import SwiftUI

/// Main tab: GPT-style agent chat. All input flows through here; assistant
/// replies render as plain text, DB writes render as confirmation cards.
struct ChatView: View {
    @StateObject private var viewModel: ChatViewModel
    @State private var photoSelection: PhotosPickerItem?
    @FocusState private var inputFocused: Bool

    init(configuration: AppConfiguration) {
        _viewModel = StateObject(wrappedValue: ChatViewModel(configuration: configuration))
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                messageList
                inputBar
            }
            .background(OMP.concrete)
            .navigationTitle("OhMyPT")
            .navigationBarTitleDisplayMode(.inline)
            .task { await viewModel.loadHistory() }
        }
    }

    private var messageList: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 14) {
                    if viewModel.isLoadingHistory {
                        ProgressView().frame(maxWidth: .infinity)
                    }
                    if viewModel.messages.isEmpty && !viewModel.isLoadingHistory {
                        emptyState
                    }
                    ForEach(viewModel.messages) { message in
                        MessageRow(message: message)
                            .id(message.id)
                    }
                    if viewModel.isSending {
                        HStack(spacing: 6) {
                            ProgressView().controlSize(.small)
                            Text("분석 중…")
                                .font(.footnote)
                                .foregroundStyle(.secondary)
                        }
                        .id("typing")
                    }
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 12)
            }
            .onChange(of: viewModel.messages) { _ in
                withAnimation {
                    proxy.scrollTo(viewModel.messages.last?.id, anchor: .bottom)
                }
            }
            .onTapGesture { inputFocused = false }
        }
    }

    private var emptyState: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("무엇이든 던져보세요")
                .font(.headline)
            Text("“닭가슴살 샐러드 먹었어”, “하체 운동 50분 했어”, 식단·운동·인바디 사진 — 말하거나 찍으면 자동으로 기록됩니다.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .padding(.top, 32)
    }

    private var inputBar: some View {
        VStack(spacing: 8) {
            if let image = viewModel.pendingImage {
                HStack {
                    Image(uiImage: image)
                        .resizable()
                        .scaledToFill()
                        .frame(width: 52, height: 52)
                        .clipShape(RoundedRectangle(cornerRadius: 10))
                    Button {
                        viewModel.pendingImage = nil
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                }
                .padding(.horizontal, 16)
            }

            HStack(spacing: 10) {
                PhotosPicker(selection: $photoSelection, matching: .images) {
                    Image(systemName: "plus.circle.fill")
                        .font(.system(size: 26))
                        .foregroundStyle(.secondary)
                }
                .onChange(of: photoSelection) { newItem in
                    guard let newItem else { return }
                    Task {
                        if let data = try? await newItem.loadTransferable(type: Data.self),
                           let uiImage = UIImage(data: data) {
                            await MainActor.run { viewModel.pendingImage = uiImage }
                        }
                        photoSelection = nil
                    }
                }

                TextField("무엇이든 기록하거나 물어보세요", text: $viewModel.draft, axis: .vertical)
                    .lineLimit(1...4)
                    .focused($inputFocused)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 9)
                    .background(
                        RoundedRectangle(cornerRadius: 20)
                            .fill(Color(.systemGray6))
                    )

                Button {
                    Task { await viewModel.send() }
                } label: {
                    Image(systemName: "arrow.up.circle.fill")
                        .font(.system(size: 28))
                        .foregroundStyle(canSend ? Color.accentColor : Color(.systemGray4))
                }
                .disabled(!canSend)
            }
            .padding(.horizontal, 16)
            .padding(.bottom, 8)
        }
        .background(.bar)
    }

    private var canSend: Bool {
        !viewModel.isSending &&
        (!viewModel.draft.trimmingCharacters(in: .whitespaces).isEmpty || viewModel.pendingImage != nil)
    }
}

private struct MessageRow: View {
    let message: ChatMessage

    var body: some View {
        VStack(alignment: message.isUser ? .trailing : .leading, spacing: 8) {
            if !message.content.isEmpty {
                Text(message.content)
                    .font(.body)
                    .padding(message.isUser ? EdgeInsets(top: 9, leading: 14, bottom: 9, trailing: 14) : EdgeInsets())
                    .background(
                        message.isUser
                            ? AnyView(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(OMP.panel))
                            : AnyView(EmptyView())
                    )
                    .foregroundStyle(message.isUser ? Color.white : OMP.ink)
                    .frame(maxWidth: .infinity, alignment: message.isUser ? .trailing : .leading)
            }
            ForEach(message.cards) { card in
                ChatCardView(card: card)
            }
        }
        .frame(maxWidth: .infinity, alignment: message.isUser ? .trailing : .leading)
    }
}

private struct ChatCardView: View {
    let card: ChatCard

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(card.title)
                .font(.caption.weight(.bold))
                .foregroundStyle(.white)
                .padding(.horizontal, 8)
                .padding(.vertical, 3)
                .background(OMP.panel, in: RoundedRectangle(cornerRadius: 5, style: .continuous))

            ForEach(Array(card.rows.enumerated()), id: \.offset) { _, row in
                if row.count >= 2 {
                    HStack(alignment: .top) {
                        Text(cleanHTML(row[0]))
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                        Spacer(minLength: 12)
                        Text(cleanHTML(row[1]))
                            .font(.footnote.weight(.semibold))
                            .monospacedDigit()
                            .multilineTextAlignment(.trailing)
                    }
                }
            }

            if let meta = card.meta, !meta.isEmpty {
                Text(meta)
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .fill(OMP.sheet)
                .overlay(
                    RoundedRectangle(cornerRadius: 10, style: .continuous)
                        .strokeBorder(OMP.hairline, lineWidth: 1)
                )
        )
    }

    /// Server card values may carry Telegram-style tags (<b>, <i>) — strip them.
    private func cleanHTML(_ text: String) -> String {
        text.replacingOccurrences(of: "<[^>]+>", with: "", options: .regularExpression)
            .replacingOccurrences(of: "&amp;", with: "&")
    }
}
