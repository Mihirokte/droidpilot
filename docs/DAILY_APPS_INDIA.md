# Daily phone tasks in India: what droidpilot can do

This file lists everyday phone tasks for people in India and how well droidpilot handles each one.

- **Tested** means a real agent (Kiro CLI, Claude Sonnet 5.5) did the task on a realme 9 with Android 14, from one plain sentence.
- **Untested** means the app is not on the test phone, or the task needs a signed-in account. These rows are a plan, not a result.

## 1. Tested tasks

Each task was read-only: the agent was told to send, pay, buy, book, delete and sign in to nothing.

| Task | App | Wall time | Tool calls | Result |
|---|---|---|---|---|
| Drive time from Majestic to Bengaluru airport | Google Maps | 66 s | 13 | Correct: 47 min, 33 km, with an alternative at 57 min. The agent built a Maps link itself. |
| Top 3 results for "Bengaluru traffic news today" | YouTube | 39 s | 7 | Correct titles and channels. No video played. |
| Battery, battery saver, free storage | Settings | 65 s | 15 | Battery 100% and saver off: match `adb`. Storage was read from the Settings screen. |
| 3 cheapest cotton kurtis | Meesho | 115 s | 26 | Found ₹91 listings. The agent said the price sort was not available, and that it may have missed a row. |
| Events today and tomorrow | Google Calendar | 25 s | 5 | Correct: nothing planned. |
| Weather in Bengaluru | Chrome | 31 s | 4 | Answered: 21°, cloudy. |
| Android version | Settings | 32 s | 6 | Correct: Android 14. |
| Amazon cart, then black jeans under ₹2,000 | Amazon | 98 s | 17 | Correct. Cart unchanged. |
| First screen of the app | PhonePe | 26 s | 3 | Stopped at the mobile-number login screen, as told. |
| First screen of the app | Google Pay | 26 s | 4 | Stopped at setup, as told. |
| Note titles | Google Keep | 23 s | 3 | Stopped at Google sign-in, as told. |
| Tap "Proceed to checkout" | Amazon | 35 s | 7 | **Blocked** by the safety guard. The agent did not retry. |

## 2. What the tests found and fixed

| Problem | Effect | Fix |
|---|---|---|
| The guard missed "Proceed to checkout" and "Proceed to Buy" | A checkout step was tapped. Nothing was bought, because the account was not signed in. | Guard covers checkout, pay, UPI, booking, send, post, delete and log out. "Add to cart" and "Your orders" stay allowed. 27 labels are in a test. |
| Two agents drove one phone at the same time (my test mistake) | Each agent saw apps open by themselves. Results were wrong. | A per-phone lock. A second droidpilot gets a clear error. |
| The status bar (clock, icons) was in the UI tree | A still screen looked "changed" every minute | The status bar is removed from the tree. The notification shade stays. |
| "Wi-Fi" could not be found by `tap_text` | Hyphens were changed in the query, not on the screen | The same rule is used on both sides. |
| The new lock locked out its own server | The warm-up thread and the first tool call connected at the same time | `connect()` is serialized. The lock also waits 5 s for a server that is shutting down. |

## 3. Plan: daily task categories in India

Sorted by how often people do them and how well they fit droidpilot.

Fit:
- **High:** standard Android views, deep links exist, read-only is enough.
- **Medium:** much of the UI is drawn by web views or canvases. Use `look` or screenshots.
- **Low:** the app blocks automation or screenshots, or needs an OTP.

### Communication

| Task | Apps | Fit | Notes |
|---|---|---|---|
| Read unread messages, summarize a group chat | WhatsApp, Messages | High | Read-only is safe. A "send" is blocked by the guard until the user confirms. |
| Draft a reply, user sends | WhatsApp, Telegram | High | Open with `https://wa.me/<number>?text=...`. The guard stops "Send". |
| Who called, missed calls | Phone (Dialer) | High | Read the call log screen. |
| Delete OTP and promo SMS | Messages | Medium | Deleting needs confirmation. |

### Money (UPI and banking)

| Task | Apps | Fit | Notes |
|---|---|---|---|
| Check the last 5 UPI transactions | Google Pay, PhonePe, Paytm, BHIM | Medium | Needs a signed-in app. Bank apps often block screenshots (`FLAG_SECURE`). The UI tree can still work. |
| Pay a bill or send money | Same | **User only** | The UPI PIN must come from the user. droidpilot never enters a PIN. The guard blocks "Pay". |
| Mobile and DTH recharge, see plans | Jio, Airtel, Paytm | High (browse) | The agent compares plans. The user pays. |
| Electricity bill amount (BESCOM, MSEDCL and others) | Bill-pay apps, Paytm | Medium | Reading the due amount is safe. Paying is user-only. |

### Shopping and food

| Task | Apps | Fit | Notes |
|---|---|---|---|
| Compare a price | Amazon, Flipkart, Meesho, Myntra | High | Tested on Amazon and Meesho. Deep links with filters work on Amazon. |
| Add to cart, user checks out | Same | High | Tested on Amazon. Checkout is blocked. |
| Groceries in 10 minutes: build a basket | Blinkit, Zepto, Swiggy Instamart, BigBasket | High | Build the cart from a list. The user pays. |
| Reorder food, compare delivery fees | Swiggy, Zomato | High | "Place order" is blocked. |
| Track an order | All of the above | High | "Track order" is allowed. |

### Travel and commute

| Task | Apps | Fit | Notes |
|---|---|---|---|
| Drive time, traffic, route | Google Maps | High | Tested. Use `open_url` with a Maps directions link. |
| Compare cab prices | Uber, Ola, Rapido | High (compare) | Booking is blocked. |
| Train PNR status, seat availability | IRCTC Rail Connect, ixigo, ConfirmTkt, Where is my Train | Medium | IRCTC login needs a CAPTCHA and an OTP: `NEEDS_HUMAN`. PNR lookup in third-party apps has no login. |
| Metro card balance, next train | Namma Metro, DMRC | Medium | Varies by city. |
| FASTag balance | Bank or Paytm FASTag | Medium | Read-only. |

### Government and documents

| Task | Apps | Fit | Notes |
|---|---|---|---|
| Find a document (PAN, driving licence) | DigiLocker | Low | OTP login. Shows documents in a secure view. |
| Government services | UMANG | Low | OTP login. |
| Aadhaar status | mAadhaar | Low | OTP. Never automate the Aadhaar number or OTP entry. |

### Media and daily information

| Task | Apps | Fit | Notes |
|---|---|---|---|
| Search a video, list results | YouTube | High | Tested. |
| Cricket score | Cricbuzz, Google search in Chrome | High | Chrome plus `web_read` is the fastest path. |
| News in a regional language | Dailyhunt, Google News, Inshorts | High | Kannada, Hindi and others come through the UI tree as Unicode. |
| Weather | Chrome, Weather app | High | Tested. |

### Phone care

| Task | Apps | Fit | Notes |
|---|---|---|---|
| Battery, storage, Android version | Settings | High | Tested. |
| Calendar for today | Google Calendar | High | Tested. |
| Set an alarm or a reminder | Clock, Calendar | High | Not a payment or a message, so the guard allows it. |
| Clear app cache, find big files | Files by Google | Medium | Deleting is blocked until confirmed. |

## 4. Limits to expect in India

- **OTP and UPI PIN.** Most Indian apps log in with an OTP. droidpilot returns `NEEDS_HUMAN` and the user types it. droidpilot must never read OTPs from SMS and type them in without the user.
- **Secure screens.** Bank, UPI and DigiLocker screens often block screenshots. `observe` (the UI tree) may still work. `look` and screenshots show black.
- **Language.** Many apps ask for a language on first start (the Meesho run did). The agent chose English. Regional-language text is read correctly.
- **Permission prompts.** First starts ask for location, contacts and notifications. The agents in the tests chose "Don't allow" or "Skip". That is the safe default.
- **OEM pop-ups.** realme showed a "32-bit app" warning over PhonePe. Other brands (Xiaomi, Vivo, Samsung) show their own pop-ups.
- **One agent per phone.** Run tasks one after the other.

## 5. Suggested next tests

These need apps that are not on the test phone, or a signed-in account:

1. WhatsApp: summarize unread chats, read-only.
2. Blinkit or Zepto: build a basket from a list of 5 items, stop at checkout.
3. IRCTC or ixigo: PNR status by number.
4. Swiggy or Zomato: compare the delivery fee for one dish at 3 restaurants.
5. Uber, Ola and Rapido: compare the fare for one route.
