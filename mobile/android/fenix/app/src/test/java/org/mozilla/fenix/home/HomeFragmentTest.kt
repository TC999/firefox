/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

package org.mozilla.fenix.home

import android.content.Context
import io.mockk.every
import io.mockk.mockk
import io.mockk.spyk
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.mozilla.fenix.FenixApplication
import org.mozilla.fenix.HomeActivity
import org.mozilla.fenix.components.Core
import org.mozilla.fenix.components.appstate.AppAction
import org.mozilla.fenix.components.appstate.AppState
import org.mozilla.fenix.ext.application
import org.mozilla.fenix.ext.components
import org.mozilla.fenix.reviewprompt.ReviewPromptState
import org.mozilla.fenix.reviewprompt.ReviewPromptState.Eligible.Type
import org.mozilla.fenix.utils.Settings

class HomeFragmentTest {

    private lateinit var settings: Settings
    private lateinit var context: Context
    private lateinit var core: Core
    private lateinit var homeFragment: HomeFragment

    @Before
    fun setup() {
        settings = mockk(relaxed = true)
        context = mockk(relaxed = true)
        core = mockk(relaxed = true)

        val fenixApplication: FenixApplication = mockk(relaxed = true)

        homeFragment = spyk(HomeFragment())

        every { context.application } returns fenixApplication
        every { homeFragment.context } answers { context }
        every { context.components.settings } answers { settings }
        every { context.components.core } answers { core }
        every { homeFragment.binding } returns mockk(relaxed = true)
        every { homeFragment.viewLifecycleOwner } returns mockk(relaxed = true)
    }

    @Test
    fun `GIVEN the user is in normal mode WHEN checking if should enable wallpaper THEN return true`() {
        val activity: HomeActivity = mockk {
            every { themeManager.currentTheme.isPrivate } returns false
        }
        every { homeFragment.activity } returns activity

        assertTrue(homeFragment.shouldEnableWallpaper())
    }

    @Test
    fun `GIVEN the user is in private mode WHEN checking if should enable wallpaper THEN return false`() {
        val activity: HomeActivity = mockk {
            every { themeManager.currentTheme.isPrivate } returns true
        }
        every { homeFragment.activity } returns activity

        assertFalse(homeFragment.shouldEnableWallpaper())
    }

    @Test
    fun `WHEN isMicrosurveyEnabled is true GIVEN a call to initializeMicrosurveyFeature THEN messagingFeature is initialized`() {
        assertNull(homeFragment.messagingFeatureMicrosurvey.get())

        homeFragment.initializeMicrosurveyFeature(isMicrosurveyEnabled = true)

        assertNotNull(homeFragment.messagingFeatureMicrosurvey.get())
    }

    @Test
    fun `WHEN isMicrosurveyEnabled is false GIVEN a call to initializeMicrosurveyFeature THEN messagingFeature is not initialized`() {
        assertNull(homeFragment.messagingFeatureMicrosurvey.get())

        homeFragment.initializeMicrosurveyFeature(isMicrosurveyEnabled = false)

        assertNull(homeFragment.messagingFeatureMicrosurvey.get())
    }

    @Test
    fun `GIVEN observing review prompt state WHEN eligible for custom prompt THEN custom prompt shown`() {
        runTest {
            val actions = mutableListOf<AppAction>()
            var playStorePromptShown = false
            var customPromptShown = false

            homeFragment.observeReviewPromptState(
                appStates = flowOf(AppState(reviewPrompt = ReviewPromptState.Eligible(Type.Custom))),
                dispatchAction = { actions += it },
                tryShowPlayStorePrompt = { playStorePromptShown = true },
                showCustomPrompt = { customPromptShown = true },
            )

            assertTrue(customPromptShown)
            assertFalse(playStorePromptShown)
            assertTrue(actions.contains(AppAction.ReviewPromptAction.ReviewPromptShown))
        }
    }

    @Test
    fun `GIVEN observing review prompt state WHEN eligible for Play Store prompt THEN Play Store prompt shown`() {
        runTest {
            val actions = mutableListOf<AppAction>()
            var playStorePromptShown = false
            var customPromptShown = false

            homeFragment.observeReviewPromptState(
                appStates = flowOf(AppState(reviewPrompt = ReviewPromptState.Eligible(Type.PlayStore))),
                dispatchAction = { actions += it },
                tryShowPlayStorePrompt = { playStorePromptShown = true },
                showCustomPrompt = { customPromptShown = true },
            )

            assertTrue(playStorePromptShown)
            assertFalse(customPromptShown)
            assertTrue(actions.contains(AppAction.ReviewPromptAction.ReviewPromptShown))
        }
    }

    @Test
    fun `GIVEN observing review prompt state WHEN state is unknown THEN does nothing`() {
        runTest {
            val actions = mutableListOf<AppAction>()
            var promptShown = false

            homeFragment.observeReviewPromptState(
                appStates = flowOf(AppState(reviewPrompt = ReviewPromptState.Unknown)),
                dispatchAction = { actions += it },
                tryShowPlayStorePrompt = { promptShown = true },
                showCustomPrompt = { promptShown = true },
            )

            assertFalse(promptShown)
            assertEquals(emptyList<AppAction>(), actions)
        }
    }

    @Test
    fun `GIVEN observing review prompt state WHEN not eligible THEN does nothing`() {
        runTest {
            val actions = mutableListOf<AppAction>()
            var promptShown = false

            homeFragment.observeReviewPromptState(
                appStates = flowOf(AppState(reviewPrompt = ReviewPromptState.NotEligible)),
                dispatchAction = { actions += it },
                tryShowPlayStorePrompt = { promptShown = true },
                showCustomPrompt = { promptShown = true },
            )

            assertFalse(promptShown)
            assertEquals(emptyList<AppAction>(), actions)
        }
    }
}
