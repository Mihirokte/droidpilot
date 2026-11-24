"""Device-state parser, using output captured from a real realme 9."""

from __future__ import annotations

from droidpilot import state

REAL_LOCKED = """  mWakefulness=Dozing
  mCurrentFocus=Window{572d778 u0 NotificationShade}
  mFocusedApp=ActivityRecord{53d5723 u0 in.amazon.mShop.android.shopping/com.amazon.mShop.navigation.MainActivity t24}
        isKeyguardShowing=true
    mRotation=0 mDeferredRotationPauseCount=0
  mInputShown=false
Physical size: 1080x2400
"""


REAL_AWAKE_LANDSCAPE = """  mWakefulness=Awake
  mCurrentFocus=Window{a1b2c3 u0 com.android.settings/com.android.settings.Settings}
  mFocusedApp=ActivityRecord{ff u0 com.android.settings/com.android.settings.Settings t9}
        isKeyguardShowing=false
    mRotation=1 mDeferredRotationPauseCount=0
  mInputShown=true
Physical size: 1080x2400
"""



def test_state_parses_real_locked_screen_off() -> None:
    st = state.parse(REAL_LOCKED)
    assert not st.awake and st.locked and st.rotation == 0 and not st.keyboard
    assert st.focus == "NotificationShade"
    assert st.app == "in.amazon.mShop.android.shopping/com.amazon.mShop.navigation.MainActivity"
    assert st.size == (1080, 2400)



def test_state_swaps_size_in_landscape_and_reads_keyboard() -> None:
    st = state.parse(REAL_AWAKE_LANDSCAPE)
    assert st.awake and not st.locked and st.keyboard
    assert st.rotation == 1 and st.size == (2400, 1080)
    assert st.app == "com.android.settings/com.android.settings.Settings"
    assert "keyboard=open" in st.banner()



def test_state_survives_empty_output() -> None:
    st = state.parse("")
    assert st.wakefulness == "Unknown" and not st.awake and st.size is None
