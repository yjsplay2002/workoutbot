import SwiftUI
import UIKit

/// Terminal-wayfinding visual world, shared with the web dashboard.
/// Yellow is reserved for goal wayfinding; data lives on jet-black boards;
/// content sits on sheets over a concrete ground.
///
/// The world has two lightings. In light the ground is pale concrete and sheets
/// are white; in dark the ground goes to night asphalt and sheets to slate, while
/// the yellow sign band and the jet-black data board keep their fixed values — a
/// terminal sign reads the same at noon and at midnight. Every surface token
/// below therefore carries both values, and every ink token inverts with them, so
/// no text is ever asked to sit on a surface that moved without it.
enum OMP {
    // MARK: Fixed — sign band and data board are the same under both lightings.

    static let yellow = Color(red: 1.0, green: 0.788, blue: 0.0)          // #FFC900
    static let yellowDeep = Color(red: 0.914, green: 0.722, blue: 0.0)    // #E9B800
    static let yellowInk = Color(red: 0.4, green: 0.314, blue: 0.0)       // #665000
    static let panelLine = Color(red: 0.227, green: 0.227, blue: 0.216)   // #3A3A37
    static let onPanel2 = Color(red: 0.722, green: 0.722, blue: 0.69)     // #B8B8B0
    static let greenOnPanel = Color(red: 0.482, green: 0.847, blue: 0.627) // #7BD8A0
    static let redOnPanel = Color(red: 1.0, green: 0.478, blue: 0.42)     // #FF7A6B

    /// The board stays the darkest surface in either lighting, so it reads as a
    /// board and not as a hole — in dark it drops slightly below the ground.
    static let panel = adaptive(light: 0x0E0E0D, dark: 0x0B0B0A)
    static let panel2 = adaptive(light: 0x242422, dark: 0x1A1A18)

    // MARK: Surfaces — ground, sheet, inset, and the line between them.

    static let concrete = adaptive(light: 0xEDEDE9, dark: 0x161614)
    static let sheet = adaptive(light: 0xFFFFFF, dark: 0x212120)
    static let inset = adaptive(light: 0xF4F4F0, dark: 0x2B2B29)
    static let hairline = adaptive(light: 0xD9D9D2, dark: 0x383833)

    // MARK: Inks — invert with the surfaces they sit on.

    static let ink = adaptive(light: 0x151513, dark: 0xF2F2EE)
    static let ink2 = adaptive(light: 0x5D5D57, dark: 0xA5A59C)

    // MARK: Status — lifted in dark so they clear the surface behind them.

    static let green = adaptive(light: 0x0E7A3C, dark: 0x7BD8A0)
    static let red = adaptive(light: 0xC42B1C, dark: 0xFF7A6B)
    static let amberText = adaptive(light: 0x9A6B00, dark: 0xE8B23A)

    private static func adaptive(light: Int, dark: Int) -> Color {
        Color(uiColor: UIColor { traits in
            traits.userInterfaceStyle == .dark ? UIColor(hex: dark) : UIColor(hex: light)
        })
    }
}

private extension UIColor {
    convenience init(hex: Int) {
        self.init(
            red: CGFloat((hex >> 16) & 0xFF) / 255,
            green: CGFloat((hex >> 8) & 0xFF) / 255,
            blue: CGFloat(hex & 0xFF) / 255,
            alpha: 1
        )
    }
}

// MARK: - Sign band (yellow wayfinding panel)

struct SignBand<Content: View>: View {
    var showArrow = true
    @ViewBuilder let content: Content

    var body: some View {
        HStack(alignment: .center, spacing: 14) {
            content
            if showArrow {
                Spacer(minLength: 8)
                Image(systemName: "arrow.right")
                    .font(.system(size: 24, weight: .heavy))
                    .foregroundStyle(OMP.panel)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(18)
        .background(OMP.yellow, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
    }
}

/// Black inset square carrying a white pictogram — the sign system's icon unit.
struct PictoInset: View {
    let systemImage: String
    var size: CGFloat = 40
    var onYellow = false

    var body: some View {
        Image(systemName: systemImage)
            .font(.system(size: size * 0.5, weight: .bold))
            .foregroundStyle(onYellow ? OMP.yellow : .white)
            .frame(width: size, height: size)
            .background(OMP.panel, in: RoundedRectangle(cornerRadius: size * 0.18, style: .continuous))
    }
}

// MARK: - Black data board

struct BoardCell: View {
    let label: String
    let value: String
    var unit: String? = nil
    var valueColor: Color = .white
    var gate = false

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(.caption.weight(.semibold))
                .foregroundStyle(OMP.onPanel2)
            HStack(alignment: .firstTextBaseline, spacing: 3) {
                Text(value)
                    .font(gate
                          ? .system(size: 40, weight: .heavy).monospacedDigit()
                          : .title3.weight(.heavy).monospacedDigit())
                    .foregroundStyle(valueColor)
                    .lineLimit(1)
                    .minimumScaleFactor(0.6)
                if let unit {
                    Text(unit)
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(OMP.onPanel2)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

extension View {
    /// Jet-black data board container. The edge line is invisible against the
    /// pale ground of light mode and does the separating work in dark, where
    /// board and ground are only a few points apart.
    func boardStyle() -> some View {
        self
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(OMP.panel, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .stroke(OMP.panelLine, lineWidth: 1)
            }
    }

    /// Primary action: the ink/sheet pair inverted, so the button is always the
    /// hardest contrast on screen. `.borderedProminent` can't do this — it fills
    /// with the accent colour and always draws a white label, which collapses
    /// the moment the accent goes light in dark mode.
    func ompProminent() -> some View {
        self
            .font(.subheadline.weight(.bold))
            .foregroundStyle(OMP.sheet)
            .padding(.vertical, 12)
            .frame(maxWidth: .infinity)
            .background(OMP.ink, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
    }

    /// Secondary action: ink label inside a hairline box.
    func ompSecondary() -> some View {
        self
            .font(.subheadline.weight(.semibold))
            .foregroundStyle(OMP.ink)
            .padding(.vertical, 12)
            .padding(.horizontal, 16)
            .background(OMP.inset, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .stroke(OMP.hairline, lineWidth: 1)
            }
    }

    /// White content sheet on the concrete ground (replaces the old cardStyle).
    func sheetStyle() -> some View {
        self
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(OMP.sheet, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .stroke(OMP.hairline, lineWidth: 1)
            }
    }
}
