import SwiftUI

/// Terminal-wayfinding visual world, shared with the web dashboard.
/// Yellow is reserved for goal wayfinding; data lives on jet-black boards;
/// content sits on white sheets over a concrete ground.
enum OMP {
    static let yellow = Color(red: 1.0, green: 0.788, blue: 0.0)          // #FFC900
    static let yellowDeep = Color(red: 0.914, green: 0.722, blue: 0.0)    // #E9B800
    static let yellowInk = Color(red: 0.4, green: 0.314, blue: 0.0)       // #665000
    static let panel = Color(red: 0.055, green: 0.055, blue: 0.051)       // #0E0E0D
    static let panel2 = Color(red: 0.141, green: 0.141, blue: 0.133)      // #242422
    static let panelLine = Color(red: 0.227, green: 0.227, blue: 0.216)   // #3A3A37
    static let onPanel2 = Color(red: 0.722, green: 0.722, blue: 0.69)     // #B8B8B0
    static let concrete = Color(red: 0.929, green: 0.929, blue: 0.914)    // #EDEDE9
    static let sheet = Color.white
    static let inset = Color(red: 0.957, green: 0.957, blue: 0.941)       // #F4F4F0
    static let ink = Color(red: 0.082, green: 0.082, blue: 0.075)         // #151513
    static let ink2 = Color(red: 0.365, green: 0.365, blue: 0.341)        // #5D5D57
    static let hairline = Color(red: 0.851, green: 0.851, blue: 0.824)    // #D9D9D2
    static let green = Color(red: 0.055, green: 0.478, blue: 0.235)       // #0E7A3C
    static let red = Color(red: 0.769, green: 0.169, blue: 0.11)          // #C42B1C
    static let amberText = Color(red: 0.604, green: 0.42, blue: 0.0)      // #9A6B00
    static let greenOnPanel = Color(red: 0.482, green: 0.847, blue: 0.627) // #7BD8A0
    static let redOnPanel = Color(red: 1.0, green: 0.478, blue: 0.42)     // #FF7A6B
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
    /// Jet-black data board container.
    func boardStyle() -> some View {
        self
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(OMP.panel, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
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
