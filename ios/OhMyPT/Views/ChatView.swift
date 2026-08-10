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
            messageList
                .background(OMP.concrete)
                .safeAreaInset(edge: .bottom, spacing: 0) {
                    inputBar
                }
                .navigationTitle("코치")
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
                                .foregroundStyle(OMP.ink2)
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
        VStack(alignment: .leading, spacing: 14) {
            SignBand(showArrow: false) {
                PictoInset(systemImage: "bubble.left.and.text.bubble.right.fill", size: 46, onYellow: true)
                VStack(alignment: .leading, spacing: 2) {
                    Text("말하면 기록됩니다")
                        .font(.title3.weight(.heavy))
                        .foregroundStyle(OMP.panel)
                    Text("식단 · 운동 · 인바디 — 텍스트나 사진 한 번")
                        .font(.footnote.weight(.semibold))
                        .foregroundStyle(OMP.yellowInk)
                }
                Spacer(minLength: 0)
            }

            VStack(alignment: .leading, spacing: 8) {
                Text("이렇게 보내보세요")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(OMP.ink2)
                suggestionChip("닭가슴살 샐러드 먹었어")
                suggestionChip("하체 운동 50분 했어")
                suggestionChip("오늘 단백질 얼마나 먹었어?")
                suggestionChip("남은 칼로리로 저녁 뭐 먹을까?")
            }
        }
        .padding(.top, 8)
    }

    private func suggestionChip(_ text: String) -> some View {
        Button {
            viewModel.draft = text
            inputFocused = true
        } label: {
            HStack(spacing: 8) {
                Text(text)
                    .font(.subheadline)
                    .foregroundStyle(OMP.ink)
                Spacer(minLength: 0)
                Image(systemName: "arrow.up.left")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(OMP.ink2)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .background(OMP.sheet, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .stroke(OMP.hairline, lineWidth: 1)
            }
        }
        .buttonStyle(.plain)
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
                            .foregroundStyle(OMP.ink2)
                    }
                    Spacer()
                }
                .padding(.horizontal, 16)
            }

            HStack(spacing: 10) {
                PhotosPicker(selection: $photoSelection, matching: .images) {
                    Image(systemName: "plus.circle.fill")
                        .font(.system(size: 26))
                        .foregroundStyle(OMP.ink2)
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
                        RoundedRectangle(cornerRadius: 20, style: .continuous)
                            .fill(OMP.inset)
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
        .padding(.top, 8)
        .background(OMP.sheet)
        .overlay(alignment: .top) {
            Rectangle().fill(OMP.hairline).frame(height: 1)
        }
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
                            .foregroundStyle(OMP.ink2)
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
                    .foregroundStyle(OMP.ink2.opacity(0.7))
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
