import SwiftUI
import UIKit

struct PhotoUploadView: View {
    let configuration: AppConfiguration
    @StateObject private var viewModel = ComposeViewModel()
    @Environment(\.dismiss) private var dismiss

    @State private var showCamera = false
    @State private var showResult = false

    private var cameraAvailable: Bool {
        UIImagePickerController.isSourceTypeAvailable(.camera)
    }

    var body: some View {
        Form {
            Section {
                if let image = viewModel.selectedImage {
                    Image(uiImage: image)
                        .resizable()
                        .scaledToFit()
                        .frame(maxHeight: 260)
                        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                        .listRowInsets(EdgeInsets(top: 8, leading: 8, bottom: 8, trailing: 8))
                } else {
                    StateMessageView(
                        title: "사진 선택",
                        message: "운동 기록, 식단, 인바디 사진을 올려 주세요.",
                        systemImage: "camera.viewfinder"
                    )
                    .listRowBackground(Color.clear)
                }
            }

            Section("사진 가져오기") {
                if cameraAvailable {
                    Button {
                        showCamera = true
                    } label: {
                        Label("카메라 촬영", systemImage: "camera.fill")
                    }
                }

                LibraryImagePicker(image: $viewModel.selectedImage)

                if viewModel.selectedImage != nil {
                    Button(role: .destructive) {
                        viewModel.selectedImage = nil
                    } label: {
                        Label("사진 지우기", systemImage: "trash")
                    }
                }
            }

            Section("캡션 (선택)") {
                TextField("예: 벤치프레스 60kg 10회 4세트", text: $viewModel.caption, axis: .vertical)
                    .lineLimit(3...6)
            }

            if let error = viewModel.errorMessage {
                Section {
                    Text(error)
                        .foregroundStyle(OMP.red)
                        .font(.subheadline)
                }
            }

            Section {
                Button {
                    Task {
                        await viewModel.upload(configuration: configuration)
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
                            Label("업로드 & 분석", systemImage: "arrow.up.circle.fill")
                        }
                        Spacer()
                    }
                }
                .disabled(viewModel.selectedImage == nil || viewModel.isSubmitting)
            } footer: {
                Text("서버가 사진 유형(운동/식단/인바디)을 자동 분류한 뒤 분석·저장합니다.")
            }
        }
        .navigationTitle("사진 기록")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .navigationBarLeading) {
                Button("닫기") { dismiss() }
            }
        }
        .fullScreenCover(isPresented: $showCamera) {
            CameraImagePicker(image: $viewModel.selectedImage)
                .ignoresSafeArea()
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
