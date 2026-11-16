package io.github.bryfur.tangav.ui

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** A live state, coloured by how it stands: not a setting, not an explanation (as on the page). */
enum class St { OK, BUSY, BAD, IDLE }

@Composable
fun Chip(text: String, st: St, modifier: Modifier = Modifier, big: Boolean = false) {
    val p = LocalPal.current
    val c = when (st) { St.OK -> p.ok; St.BUSY -> p.warn; St.BAD -> p.bad; St.IDLE -> p.dim }
    Row(
        modifier.clip(RoundedCornerShape(50)).background(c.copy(alpha = .14f))
            .padding(horizontal = if (big) 10.dp else 8.dp, vertical = if (big) 3.dp else 1.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(6.dp).clip(CircleShape).background(c))
        Spacer(Modifier.width(6.dp))
        Text(text, color = c, fontSize = if (big) 13.sp else 12.sp, maxLines = 1)
    }
}

/** A group's heading, with the group's reset (faint until something in it differs from its default). */
@Composable
fun Heading(title: String, onReset: (() -> Unit)? = null, canReset: Boolean = false) {
    val p = LocalPal.current
    Row(Modifier.fillMaxWidth().padding(start = 4.dp, top = 22.dp, bottom = 6.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(title.uppercase(), color = p.dim, fontSize = 11.sp, fontWeight = FontWeight.SemiBold, letterSpacing = 1.sp,
            modifier = Modifier.weight(1f))
        if (onReset != null) TextButton(onClick = onReset, enabled = canReset, modifier = Modifier.heightIn(max = 32.dp)) {
            Text("↺ Reset", fontSize = 13.sp, color = if (canReset) p.acc else p.dim.copy(alpha = .5f))
        }
    }
}

/** A card of rows, a hairline between them. */
@Composable
fun Card(content: @Composable ColumnScope.() -> Unit) {
    val p = LocalPal.current
    Column(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(p.card)
            .border(1.dp, p.line, RoundedCornerShape(12.dp)),
        content = content,
    )
}

@Composable
fun Hairline() = HorizontalDivider(color = LocalPal.current.line, thickness = 1.dp)

/**
 * A setting: its name (an i for the explanation, a reset when it is not at its default, a bar at the
 * left edge then too), a live chip under it, the control at the right (or below, where it does not fit).
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun SettingRow(
    label: String, hint: String? = null, changed: Boolean = false, onReset: (() -> Unit)? = null,
    sub: Boolean = false, below: Boolean = false, chip: (@Composable () -> Unit)? = null, control: @Composable () -> Unit,
) {
    val p = LocalPal.current
    var open by remember { mutableStateOf(false) }
    Column(
        Modifier.fillMaxWidth()
            .drawBehind { if (changed) drawRect(p.acc, Offset.Zero, Size(3.dp.toPx(), size.height)) }
            .padding(start = if (sub) 30.dp else 16.dp, end = 16.dp, top = 10.dp, bottom = 10.dp),
    ) {
        FlowRow(
            Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween,
            verticalArrangement = Arrangement.spacedBy(8.dp), itemVerticalAlignment = Alignment.CenterVertically,
        ) {
            Column(Modifier.padding(end = 12.dp).heightIn(min = 32.dp), verticalArrangement = Arrangement.Center) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(label, color = p.text, fontSize = 15.sp)
                    if (hint != null) Info(open) { open = !open }
                    if (changed && onReset != null) Text("↺", color = p.dim, fontSize = 16.sp,
                        modifier = Modifier.padding(start = 6.dp).clickable(onClick = onReset).padding(horizontal = 4.dp))
                }
                if (chip != null) Box(Modifier.padding(top = 4.dp)) { chip() }
            }
            if (!below) control()
        }
        // (a wide control, a segmented one with long names: on its own line, under the name)
        if (below) Box(Modifier.padding(top = 8.dp)) { control() }
        AnimatedVisibility(open && hint != null) {
            Text(hint ?: "", color = p.dim, fontSize = 13.sp, lineHeight = 18.sp, modifier = Modifier.padding(top = 6.dp))
        }
    }
}

@Composable
private fun Info(open: Boolean, onClick: () -> Unit) {
    val p = LocalPal.current
    val c = if (open) p.acc else p.dim
    Box(
        Modifier.padding(start = 6.dp).size(18.dp).clip(CircleShape).border(1.3.dp, c.copy(alpha = .8f), CircleShape)
            .clickable(onClick = onClick),
        contentAlignment = Alignment.Center,
    ) { Text("i", color = c, fontSize = 11.sp, fontStyle = FontStyle.Italic, fontWeight = FontWeight.Bold) }
}

/** A name and a value (the status). */
@Composable
fun KeyValue(k: String, v: String, bad: Boolean = false) {
    val p = LocalPal.current
    Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp)) {
        Text(k, color = p.dim, fontSize = 14.sp, modifier = Modifier.width(92.dp))
        Text(v, color = if (bad) p.bad else p.text, fontSize = 14.sp)
    }
}

val Transparent = Color.Transparent
