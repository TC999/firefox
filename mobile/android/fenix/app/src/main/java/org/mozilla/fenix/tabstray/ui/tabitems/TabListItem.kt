/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

package org.mozilla.fenix.tabstray.ui.tabitems

import androidx.compose.animation.core.DecayAnimationSpec
import androidx.compose.animation.rememberSplineBasedDecay
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.material3.ripple
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.tooling.preview.PreviewLightDark
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import mozilla.components.browser.state.state.TabSessionState
import mozilla.components.browser.state.state.createTab
import mozilla.components.support.base.utils.MAX_URI_LENGTH
import mozilla.components.ui.colors.PhotonColors
import org.mozilla.fenix.R
import org.mozilla.fenix.compose.DismissibleItemBackground
import org.mozilla.fenix.compose.SwipeToDismissBox2
import org.mozilla.fenix.compose.SwipeToDismissState2
import org.mozilla.fenix.compose.TabThumbnail
import org.mozilla.fenix.compose.tabstray.MediaImage
import org.mozilla.fenix.ext.toShortUrl
import org.mozilla.fenix.tabstray.TabsTrayTestTag
import org.mozilla.fenix.tabstray.ext.toDisplayTitle
import org.mozilla.fenix.theme.FirefoxTheme

/**
 * List item used to display a tab that supports clicks,
 * long clicks, multiselection, and media controls.
 *
 * @param tab The given tab to be render as view a grid item.
 * @param thumbnailSize Size of tab's thumbnail.
 * @param isSelected Indicates if the item should be render as selected.
 * @param multiSelectionEnabled Indicates if the item should be render with multi selection options,
 * enabled.
 * @param multiSelectionSelected Indicates if the item should be render as multi selection selected
 * option.
 * @param shouldClickListen Whether or not the item should stop listening to click events.
 * @param swipingEnabled Whether or not the item is swipeable.
 * @param onCloseClick Callback to handle the click event of the close button.
 * @param onMediaClick Callback to handle when the media item is clicked.
 * @param onClick Callback to handle when item is clicked.
 * @param onLongClick Optional callback to handle when item is long clicked.
 */
@OptIn(ExperimentalFoundationApi::class)
@Composable
fun TabListItem(
    tab: TabSessionState,
    thumbnailSize: Int,
    isSelected: Boolean = false,
    multiSelectionEnabled: Boolean = false,
    multiSelectionSelected: Boolean = false,
    shouldClickListen: Boolean = true,
    swipingEnabled: Boolean = true,
    onCloseClick: (tab: TabSessionState) -> Unit,
    onMediaClick: (tab: TabSessionState) -> Unit,
    onClick: (tab: TabSessionState) -> Unit,
    onLongClick: ((tab: TabSessionState) -> Unit)? = null,
) {
    val decayAnimationSpec: DecayAnimationSpec<Float> = rememberSplineBasedDecay()
    val density = LocalDensity.current
    val isRtl = LocalLayoutDirection.current == LayoutDirection.Rtl

    val swipeState = remember(multiSelectionEnabled, swipingEnabled) {
        SwipeToDismissState2(
            density = density,
            enabled = !multiSelectionEnabled && swipingEnabled,
            decayAnimationSpec = decayAnimationSpec,
            isRtl = isRtl,
        )
    }

    SwipeToDismissBox2(
        state = swipeState,
        onItemDismiss = {
            onCloseClick(tab)
        },
        backgroundContent = {
            DismissibleItemBackground(
                isSwipeActive = swipeState.swipingActive,
                isSwipingToStart = swipeState.swipingActive && swipeState.isSwipingToStart,
            )
        },
    ) {
        TabContent(
            tab = tab,
            thumbnailSize = thumbnailSize,
            isSelected = isSelected,
            multiSelectionEnabled = multiSelectionEnabled,
            multiSelectionSelected = multiSelectionSelected,
            shouldClickListen = shouldClickListen,
            onCloseClick = onCloseClick,
            onMediaClick = onMediaClick,
            onClick = onClick,
            onLongClick = onLongClick,
        )
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Suppress("LongMethod", "LongParameterList")
@Composable
private fun TabContent(
    tab: TabSessionState,
    thumbnailSize: Int,
    isSelected: Boolean,
    multiSelectionEnabled: Boolean,
    multiSelectionSelected: Boolean,
    shouldClickListen: Boolean,
    onCloseClick: (tab: TabSessionState) -> Unit,
    onMediaClick: (tab: TabSessionState) -> Unit,
    onClick: (tab: TabSessionState) -> Unit,
    onLongClick: ((tab: TabSessionState) -> Unit)? = null,
) {
    val contentBackgroundColor = if (isSelected) {
        FirefoxTheme.colors.layerAccentNonOpaque
    } else {
        FirefoxTheme.colors.layer1
    }

    // Used to propagate the ripple effect to the whole tab
    val interactionSource = remember { MutableInteractionSource() }

    val clickableModifier = if (onLongClick == null) {
        Modifier.clickable(
            enabled = shouldClickListen,
            interactionSource = interactionSource,
            indication = ripple(
                color = clickableColor(),
            ),
            onClick = { onClick(tab) },
        )
    } else {
        Modifier.combinedClickable(
            enabled = shouldClickListen,
            interactionSource = interactionSource,
            indication = ripple(
                color = clickableColor(),
            ),
            onLongClick = { onLongClick(tab) },
            onClick = { onClick(tab) },
        )
    }

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(FirefoxTheme.colors.layer3)
            .background(contentBackgroundColor)
            .then(clickableModifier)
            .padding(start = 16.dp, top = 8.dp, bottom = 8.dp)
            .testTag(TabsTrayTestTag.TAB_ITEM_ROOT)
            .semantics {
                selected = isSelected
            },
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Thumbnail(
            tab = tab,
            size = thumbnailSize,
            multiSelectionEnabled = multiSelectionEnabled,
            isSelected = multiSelectionSelected,
            onMediaIconClicked = { onMediaClick(it) },
            interactionSource = interactionSource,
        )

        Column(
            modifier = Modifier
                .padding(start = 12.dp)
                .weight(weight = 1f),
        ) {
            Text(
                text = tab.toDisplayTitle().take(MAX_URI_LENGTH),
                color = FirefoxTheme.colors.textPrimary,
                style = FirefoxTheme.typography.body1,
                overflow = TextOverflow.Ellipsis,
                maxLines = 2,
            )

            Text(
                text = tab.content.url.toShortUrl(),
                color = FirefoxTheme.colors.textSecondary,
                style = FirefoxTheme.typography.body2,
                overflow = TextOverflow.Ellipsis,
                maxLines = 1,
            )
        }

        if (!multiSelectionEnabled) {
            IconButton(
                onClick = { onCloseClick(tab) },
                modifier = Modifier
                    .size(size = 48.dp)
                    .testTag(TabsTrayTestTag.TAB_ITEM_CLOSE),
            ) {
                Icon(
                    painter = painterResource(id = R.drawable.mozac_ic_cross_24),
                    contentDescription = stringResource(
                        id = R.string.close_tab_title,
                        tab.toDisplayTitle(),
                    ),
                    tint = FirefoxTheme.colors.iconPrimary,
                )
            }
        } else {
            Spacer(modifier = Modifier.size(48.dp))
        }
    }
}

@Composable
private fun clickableColor() = when (isSystemInDarkTheme()) {
    true -> PhotonColors.White
    false -> PhotonColors.Black
}

@Composable
private fun Thumbnail(
    tab: TabSessionState,
    size: Int,
    multiSelectionEnabled: Boolean,
    isSelected: Boolean,
    onMediaIconClicked: ((TabSessionState) -> Unit),
    interactionSource: MutableInteractionSource,
) {
    Box {
        TabThumbnail(
            tab = tab,
            size = size,
            modifier = Modifier
                .size(width = 92.dp, height = 72.dp)
                .testTag(TabsTrayTestTag.TAB_ITEM_THUMBNAIL),
            contentDescription = stringResource(id = R.string.mozac_browser_tabstray_open_tab),
        )

        if (isSelected) {
            Box(
                modifier = Modifier
                    .size(width = 92.dp, height = 72.dp)
                    .clip(RoundedCornerShape(4.dp))
                    .background(FirefoxTheme.colors.layerAccentNonOpaque),
            )

            Card(
                modifier = Modifier
                    .size(size = 40.dp)
                    .align(alignment = Alignment.Center),
                shape = CircleShape,
                colors = CardDefaults.cardColors(containerColor = FirefoxTheme.colors.layerAccent),
            ) {
                Icon(
                    painter = painterResource(id = R.drawable.mozac_ic_checkmark_24),
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(all = 8.dp),
                    contentDescription = null,
                    tint = FirefoxTheme.colors.iconActionPrimary,
                )
            }
        }

        if (!multiSelectionEnabled) {
            MediaImage(
                tab = tab,
                onMediaIconClicked = onMediaIconClicked,
                modifier = Modifier.align(Alignment.TopEnd),
                interactionSource = interactionSource,
            )
        }
    }
}

@Composable
@PreviewLightDark
private fun TabListItemPreview() {
    FirefoxTheme {
        TabListItem(
            tab = createTab(url = "www.mozilla.com", title = "Mozilla"),
            thumbnailSize = 108,
            onCloseClick = {},
            onMediaClick = {},
            onClick = {},
        )
    }
}

@Composable
@PreviewLightDark
private fun SelectedTabListItemPreview() {
    FirefoxTheme {
        TabListItem(
            tab = createTab(url = "www.mozilla.com", title = "Mozilla"),
            thumbnailSize = 108,
            onCloseClick = {},
            onMediaClick = {},
            onClick = {},
            multiSelectionEnabled = true,
            multiSelectionSelected = true,
        )
    }
}
