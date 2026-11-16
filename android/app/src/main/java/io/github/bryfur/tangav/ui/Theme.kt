package io.github.bryfur.tangav.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color

/** The web page's colours (page.html :root), so the app and the page look like one thing. */
data class Pal(
    val bg: Color, val card: Color, val line: Color, val text: Color, val dim: Color,
    val acc: Color, val ok: Color, val bad: Color, val warn: Color, val input: Color,
)

val DarkPal = Pal(Color(0xFF0F1115), Color(0xFF171A21), Color(0xFF262A34), Color(0xFFE7E9EE), Color(0xFF8B92A3),
    Color(0xFF5B9DFF), Color(0xFF3ECF8E), Color(0xFFFF6B6B), Color(0xFFF5B84A), Color(0xFF0F1115))
val LightPal = Pal(Color(0xFFF3F4F7), Color(0xFFFFFFFF), Color(0xFFE2E5EC), Color(0xFF1B1E26), Color(0xFF667085),
    Color(0xFF2F6FED), Color(0xFF12995F), Color(0xFFD43C3C), Color(0xFFB7791F), Color(0xFFF6F7F9))

val LocalPal = staticCompositionLocalOf { DarkPal }

@Composable
fun TangTheme(content: @Composable () -> Unit) {
    val dark = isSystemInDarkTheme()
    val p = if (dark) DarkPal else LightPal
    val scheme = (if (dark) darkColorScheme() else lightColorScheme()).copy(
        primary = p.acc, onPrimary = Color.White, background = p.bg, onBackground = p.text,
        surface = p.card, onSurface = p.text, surfaceVariant = p.input, onSurfaceVariant = p.dim,
        outline = p.line, outlineVariant = p.line, secondaryContainer = p.card, onSecondaryContainer = p.text,
        surfaceContainer = p.card, surfaceContainerHigh = p.card, surfaceContainerHighest = p.input,
        error = p.bad,
    )
    CompositionLocalProvider(LocalPal provides p) { MaterialTheme(colorScheme = scheme, content = content) }
}
