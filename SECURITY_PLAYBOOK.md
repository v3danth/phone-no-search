# Personal Security Playbook

Phones, emails and identity, compartmentalised by tier. Written 2026-11-06,
India-specific. All numbers and addresses below are placeholders.

## 0. Principles
1. **Compartmentalise.** Each identifier has one job. A leak stays inside its tier.
2. **Information only flows downward.** Tier 3 never learns about Tier 0.
3. **Any number you give a person eventually becomes public** (through
   contact-book uploads), so Tiers 0 and 1 are never given to anyone.
4. **Hard to break into and hard to lose.** Losing access to the vault is as
   bad as being hacked.
5. **Deceive data collectors, never the law.** Give real details only where
   KYC is legally required.
6. **Decoys must lead nowhere.** A trail that ends at someone close to you
   isn't a decoy; it points to you.
7. **Secrecy is a layer, not the defence.** Bank staff, call centres, sales
   agents and vendors can all see your vault number and email, and leaks
   happen. Everything must stay safe even when an attacker knows your number,
   name, bank and account details. Make the number worthless rather than
   secret: it's an alert channel, not a key.

## 1. Threat model

| # | Threat | Adversary | Severity |
|---|---|---|---|
| T1 | SIM swap | Criminals | 🔴 |
| T2 | OTP phishing / social engineering | Criminals | 🔴 |
| T3 | Aadhaar misuse (AePS fingerprint fraud, fake eKYC) | Criminals | 🟠 |
| T4 | Data brokers, breaches, leaks | Companies, criminals | 🟠 |
| T5 | Someone you know wants your number or location | People you know | 🟡 |
| T6 | Spam, scams, loan-app harassment | Criminals | 🟡 |
| T7 | Stolen or unlocked phone | Criminals | 🟠 |
| T8 | Contact-book uploads (Truecaller, Getcontact) | Platforms, via friends | 🟠 |
| T9 | Email takeover | Criminals | 🔴 |
| T10 | Accounts linked across tiers | Platforms, brokers | 🟠 |
| T11 | State access to content | Government | 🟠 |
| T12 | State access to metadata | Government | ⚠️ Accepted |
| T13 | Provider reading your data (Google and others) | Platforms | 🟡 |
| T14 | Single provider failure or lockout | Providers | 🟠 |
| T15 | People close to you targeted through shared identifiers | Criminals, people you know | 🟠 |
| T16 | Insider leak at a bank or service (staff, agents, vendors) | Insiders, criminals | 🔴 |

### What the Indian state can access (context for T11/T12)
- **Full SIM register** tied to Aadhaar or ID. **ASTR**, DoT's face-matching
  system, compares SIM KYC photos, so SIMs under different names but your face
  are also linked.
- **Call and SMS records** (who, when, which cell tower), IMEI history,
  location.
- **Lawful interception** (Telecommunications Act 2023 s.20; IT Act s.69 and
  s.69B).
- **CERT-In rules:** companies keep logs for 180 days in India; VPN, cloud and
  data-centre providers keep subscriber KYC for 5 years.
- **Aadhaar authentication history**, PAN-linked finances, bank and UPI
  records.
- **Platform data** through legal requests: Indian providers comply directly,
  US providers comply with valid orders, Swiss/German providers usually need
  an international legal-assistance request.
- **Not readable:** the content of end-to-end encrypted messages and calls,
  encrypted backups, and data that was never collected.
- **Sanchar Saathi:** the order to pre-install it on all phones was withdrawn
  in December 2025; the app is optional.

## 2. Inventory: placeholders only

| ID | Type | Value | Tier |
|---|---|---|---|
| SIM-V | SIM (own name) | `+91 XXXXX-XXXX`, all banks, cards, demat | 0 Vault |
| SIM-A | SIM (own name) | `+91 XXXXX-XXXX` | 1 Identity |
| SIM-S | SIM (own name) | `+91 XXXXX-XXXX` | 2 Social |
| SIM-P | SIM (own name) | `+91 XXXXX-XXXX` (old, widely known number) | 3 Public |
| SIM-D | SIM (own name) | `+91 XXXXX-XXXX`, receive-only decoy | 3 Public |
| SIM-F | SIM (own name, optional) | `+91 XXXXX-XXXX`, front number that forwards to SIM-S | 2 Social |
| EM-V | Proton (own account) | `v-<random>@proton.me`, with a separate address or alias per bank (`b1-<random>@…`, `b2-<random>@…`) | 0 |
| EM-A | Tuta (own account) | `a-<random>@tuta.com` | 1 |
| EM-S | Proton (own account) | `<you>@proton.me` | 2 |
| EM-P | Aliases (SimpleLogin/addy.io) | `<site>.<random>@<alias domain>` | 3 |
| PH-1 | Vault phone (GrapheneOS or iPhone with Advanced Data Protection) | SIM-V + SIM-A | 0–1 |
| PH-2 | Daily phone | SIM-S + SIM-P (SIM-D as eSIM or swapped in) | 2–3 |
| HK-1/2 | Hardware security keys (FIDO2) | One carried, one at home | 0–1 |

Total: 5–6 SIMs (the legal limit is 9 per person, 6 in J&K and the
North-East), 2 phones, 3 email accounts, one alias service.

## 3. Tier map

| | **Tier 0 Vault** | **Tier 1 Identity** | **Tier 2 Social** | **Tier 3 Public** |
|---|---|---|---|---|
| **Used for** | Banks, UPI, demat, credit cards, tax filing, CA | UIDAI, DigiLocker, passport, govt portals, insurance, employer HR | Family, close friends | Shops, apps, deliveries, forms, newsletters |
| **Phone** | SIM-V | SIM-A | Signal username; SIM-F forwarding | SIM-P (accounts you sign in to), SIM-D (strangers and counters) |
| **Email** | EM-V (Proton), one address per bank | EM-A (Tuta) | EM-S (Proton) | Aliases → EM-S |
| **Device** | PH-1 | PH-1 | PH-2 | PH-2 |
| **Apps** | Bank, UPI only | mAadhaar, DigiLocker | Signal, WhatsApp (private) | Everything else |
| **Who knows it** | Banks only (assume their staff leak it) | Govt, employer | Close people (username or front number) | Anyone |
| **Real name?** | ✅ KYC | ✅ KYC | ✅ | Decoy name allowed where there's no KYC |
| **Login** | Hardware keys + recovery phrase | Hardware keys / passkey | Passkey + authenticator app | Password manager |
| **Never** | SMS recovery, WhatsApp, Truecaller, saved in anyone's phone, **acting on an incoming call** | Saved in anyone's phone | — | Used for anything that matters |

### Vault rules (assume the number has leaked)
1. **Inbound "bank" calls are always fake**, even when the caller knows your
   account details. Hang up and call the number printed on your card.
2. **PH-1 silences unknown callers.** It's for you to make calls and use apps,
   never for taking calls.
3. **Prefer banks that tie the app to your phone** and approve in the app; avoid
   flows that rely only on SMS OTPs. A swapped SIM alone should not be enough.
4. **Low limits** on UPI, NEFT/IMPS and cards; raise them only when needed.
5. **Turn off unused features:** international use, online payments on
   shop-only cards, contactless.
6. **Keep the new-payee cooling-off** that limits transfers to new payees.
7. **Alerts on SMS, email and app**, so a SIM swap can't silence all three.
8. **An email address per bank** (free with Proton addresses or aliases), so
   a leak tells you which bank leaked. One vault SIM is enough: extra SIMs
   don't stop leaks, since every bank still knows its own number.
9. **The number is an alert channel, not a key.** With app-bound approval, low
   limits and no action on inbound contact, knowing SIM-V gets an attacker
   nothing but the ability to send you spam.

### SIM-D rules (receive-only decoy)
Someone who looks up SIM-D should find nothing but a state and a carrier:
1. **Never make calls or send SMS from it.** CNAP shows your name only on
   outgoing calls.
2. **No WhatsApp, Telegram or Signal on it**, so there's no profile, photo or
   name.
3. **Only give it to companies and strangers, never to people you know**, so
   it's never in a contact book.
4. **Opt it out of Truecaller and Getcontact** anyway.
5. **Replace it** when it gets too much spam. Nothing depends on it.
6. Check it once in a while:
   `.venv/bin/python phonelookup.py <SIM-D>` and `--dork <SIM-D>`. The result
   should be just the state, carrier and "mobile", and Google should return
   nothing.

### Other people's numbers
| Use | Allowed? |
|---|---|
| Your wife's or family's number for **shared household** things (gas, electricity, society app, family deliveries), **with consent** | ✅ |
| Their number for **your own** accounts or sign-ups | ❌ They get your OTPs, it links them to you (T15), you lose control |
| Their number for anything with KYC | ❌ |
| Any number without the owner's consent, or a random number | ❌ Never |

## 4. Email

| Tier | Provider | Notes |
|---|---|---|
| 0 Vault | Proton, its own account | The 5 vault rules below |
| 1 Identity | Tuta, its own account | A different company from the vault, so one provider can't take out both (T14) |
| 2 Personal | Proton, a different account from the vault | Everyday inbox |
| 3 Public | SimpleLogin or addy.io aliases → Tier 2 | Turn on PGP encryption of forwarded mail |

**Vault email rules:**
1. **Save the recovery phrase** on paper in two places. Without it, a password
   reset keeps the account but leaves old mail unreadable.
2. **No SMS recovery and no recovery phone.** Use the recovery phrase plus a
   recovery email (Tier 1).
3. **Two hardware keys** (FIDO2), one kept at home.
4. **Pay for a plan or log in regularly**, so a free account isn't deleted for
   inactivity (Proton can delete free accounts after 12 months without a
   login).
5. **A separate account from your personal Proton**, not an alias of it.

**General email rules:**
- Recovery chain: Tier 1's recovery can be the vault address, never the
  reverse.
- Never forward vault mail to the personal inbox.
- No "Sign in with Google/Apple" on Tier 0 or 1.
- Use a password manager (Bitwarden or 1Password).
- Turn on haveibeenpwned alerts for every address.
- **Custom domains** are fine for Tier 2 and 3, with auto-renew for 5–10 years
  and a secured registrar account. **Never for the vault:** an expired domain
  can be bought by someone else, who then receives your password resets.

**Limits:**
- Mail exchanged with Gmail users is readable by Google on their side.
- Email metadata (sender, recipient, time, and the subject line on Proton) is
  never encrypted.
- Use Signal for anything sensitive.

### Other places Google has your data
| Google service | Alternative |
|---|---|
| Android Google account | iPhone with Advanced Data Protection, or GrapheneOS on a Pixel |
| Google Contacts sync | Contacts on the device only, or Proton Contacts |
| Google Photos / Drive | Ente Photos, Proton Drive |
| WhatsApp backup | Turn on WhatsApp's end-to-end encrypted backup |
| Chrome sync / Google Pay | Firefox or Brave; Bitwarden; a UPI app other than GPay |
| Gboard | FUTO Keyboard, or a built-in keyboard with cloud features off |

## 5. Deception layer (lawful)

| Technique | How | What it protects against |
|---|---|---|
| Receive-only decoy SIM | SIM-D for counters, forms, strangers | T4, T5, T6, T15 |
| One alias per site | `swiggy.k3x@alias`, `amazon.p9q@alias` | T4, T10 |
| Canary names | `V. Swiggy`, `Ved Amazon` where real names aren't required; the name in the scam call tells you who leaked | T4 |
| Decoy details on non-KYC forms | Nickname, birth year off by one, generic city | T4, T10 |
| Canary email | One unused alias planted in one place; mail to it means that place was breached | T4, T9 |
| Canary tokens | canarytokens.org: a fake "bank statement.pdf" that alerts you when opened | T9, T11 |
| Front numbers | SIM-F forwards to SIM-S (`**21*<number>#` on, `##21#` off) | T5, T8 |
| Number rotation | Replace SIM-P or SIM-D when spam becomes unmanageable | T6 |
| Shop counters | "I don't share my number", or give SIM-D | T4, T6 |

**Red lines, all illegal or harmful:**
- Others' real numbers or emails without consent, or for your own accounts.
- Fake details for KYC: bank, telecom, govt, insurance, employer, tax.
- Someone else's SIM.
- Fake identity documents.
- Pretending to be a specific real person.

## 6. Hardening per threat

| # | Countermeasures |
|---|---|
| T1 | App-bound banking so a SIM alone isn't enough; SIM-V kept private (but assume leaked); SIM PIN; bank SIM-change alerts; no SMS recovery in Tier 0; if PH-1 shows "No service", call the bank immediately |
| T2 | Never act on inbound calls, even when the caller knows your details; PH-1 silences unknown callers; low UPI and transfer limits; always call the bank on the number on your card |
| T3 | Lock biometrics in mAadhaar; Virtual ID or masked Aadhaar; check authentication history monthly |
| T4 | SIM-D, aliases, canary names, decoy details; unlist from Truecaller, Getcontact and Google "Results about you"; haveibeenpwned alerts |
| T5 | Signal username; front number; WhatsApp profile visible only to contacts; no live location |
| T6 | DND registration; report on Sanchar Saathi Chakshu; rotate SIM-P/SIM-D |
| T7 | Hide OTP and notification content on the lock screen; app locks; strong PIN; CEIR block if stolen |
| T8 | Tier 0 and 1 never shared; contacts stored on the phone only, not synced |
| T9 | Hardware keys; no SMS recovery; vault email used for nothing else |
| T10 | No "Sign in with Google/Apple" on Tier 0/1; separate devices; aliases |
| T11 | Signal for anything sensitive; encrypted backups; disappearing messages |
| T12 | Accepted. Reduced only by keeping sensitive talk on encrypted apps instead of normal calls and SMS |
| T13 | No Gmail; Proton/Tuta; Ente or Proton Drive; no Google account on PH-1; contacts not synced |
| T14 | Vault and identity on different providers; recovery phrases on paper in 2 places; 2 hardware keys |
| T15 | Never use family's or friends' identifiers for your accounts; decoys always lead nowhere; family follows the basics too (WhatsApp privacy, unlisting) |
| T16 | Vault rules above: assume leaked; never act on inbound calls; app-bound banking; low limits; alerts on 3 channels; an email per bank to identify which bank leaked; complain to the bank, then the RBI Ombudsman |

## 7. Setup phases

Tick these off as you go.

**Week 1: Find out where you stand**
- [ ] 1. TAFCOP: list every SIM in your name and report any you don't recognise
- [ ] 2. List every account by tier, in a spreadsheet inside the password manager
- [ ] 3. Run haveibeenpwned on all current emails and numbers
- [ ] 4. Download your Google data with Google Takeout

**Week 2: Vault**
- [ ] 5. Buy 2 hardware keys and set up the password manager
- [ ] 6. Create EM-V (Proton): recovery phrase on paper ×2, both keys, no phone
- [ ] 7. Get SIM-V; set up PH-1 to silence unknown callers. Test your bank and UPI apps on it first
- [ ] 8. Change every bank, card, demat and tax account to SIM-V, each with its own EM-V address
- [ ] 9. Custom UPI ID; low limits; turn off unused card features; alerts on SMS, email and app; switch to app-based approval where offered

**Week 3: Identity**
- [ ] 10. Create EM-A (Tuta) with its recovery phrase on paper ×2
- [ ] 11. Get SIM-A; change the Aadhaar-linked mobile at an enrolment centre; lock biometrics
- [ ] 12. Change DigiLocker, the income tax portal (if not in vault), passport and employer to SIM-A + EM-A

**Week 4: Social and public**
- [ ] 13. Create EM-S (Proton) and set up SimpleLogin with PGP forwarding
- [ ] 14. Move close contacts to your Signal username; optionally set up SIM-F forwarding
- [ ] 15. Make the old number SIM-P; switch each site to its own alias, adding canary names as you go
- [ ] 16. Get SIM-D; set it up as receive-only; opt it out; check it with `phonelookup.py`
- [ ] 17. WhatsApp: profile visible to contacts only, encrypted backup on
- [ ] 18. Unlist all numbers from Truecaller, Getcontact and Google
- [ ] 19. Move any of your accounts registered to family or friends' numbers onto your own SIMs

**Months 2–6: Clean-up**
- [ ] 20. Keep the old Gmail to catch missed accounts, then delete its mail, then the account

## 8. Maintenance

| How often | Task |
|---|---|
| Monthly | Aadhaar authentication history; bank statements; note any unsolicited calls or SMS on SIM-V and any mail to a bank's address that isn't from that bank (that's a leak); check the canary alias and canary tokens |
| Quarterly | TAFCOP; haveibeenpwned; check alias leaks; test both hardware keys; check SIM-D with the lookup and search |
| Yearly | Test recovery phrases; check spare-key locations; review this plan; renew any domains |

## 9. Incident playbooks

| Event | Immediate actions |
|---|---|
| PH-1 shows "No service" suddenly (possible SIM swap) | Call bank(s) and freeze → call your carrier → **1930** (national cybercrime helpline) → file at cybercrime.gov.in. Reporting within 3 days limits your losses under RBI's zero-liability rule. |
| Phone lost or stolen | Block it through CEIR → block its SIMs with the carrier → sign that device out of all accounts → change passwords stored on it |
| Spam arrives at an alias | Turn that alias off → note which company leaked it → optionally complain under the DPDP Act once its rights are in force |
| SIM-D starts showing a name in lookups | Someone saved it in their contacts → opt it out again; if it keeps happening, replace it |
| A "bank" calls and knows your account details | Hang up, don't confirm anything → call the bank on the number on your card → check which per-bank email address any related mail reached, which tells you the leaking bank → complain to that bank's grievance officer, then the RBI Ombudsman (cms.rbi.org.in) → report the number on Chakshu |
| Unknown Aadhaar authentication | Lock biometrics → report to UIDAI (1947) → file a cybercrime report |
| Canary email or canary token fires | Assume that location is breached: rotate its passwords and check related accounts |
| Harassment from someone you know | Block them → keep screenshots → cybercrime.gov.in or police → rotate the number they know (SIM-F/SIM-P) |
| Someone contacts your family about you | Tell family not to confirm anything → note what the person knew (it tells you which identifier leaked) → report if it's harassment |
| Email account locked | Recover with the recovery phrase and backup key. This is why both exist in two places. |

## 10. Risks you're accepting
- **CNAP** shows your KYC name on outgoing calls from every SIM (4G/5G, from
  1 Nov 2026, no general opt-out). That's why SIM-D never makes calls.
- **CLIR** (hiding your caller ID) is restricted in India: it needs a
  recommendation from a senior state police intelligence officer, approval
  from DoT's TERM cell, and renewal every 12 months. It isn't a realistic
  option without a documented threat.
- **The state** can link all your SIMs (KYC, face matching, phone IMEI), see
  your call records, location and bank activity, and intercept normal calls
  and SMS lawfully.
- **Mail exchanged with Gmail users** is readable by Google on their side.
- **Banks and govt** keep their own copies of your data, and **their staff can
  and do leak it**. App-bound approval and low limits make a leaked number worthless; per-bank emails identify the source.
- **Family's own habits** (Truecaller installs, contact sync) can still leak
  whatever numbers they have. Tiers 0 and 1 are protected because they never
  have them.
- The setup is more work to run, which is the cost of the protection.

This is general guidance, not legal advice. Rules (CNAP, CLIR, the DPDP Act
phase-in) were checked in November 2026 and may change.
