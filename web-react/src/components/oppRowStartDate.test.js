import { isStartDateLocked, oppRowStartDate } from "./oppRowStartDate"

describe("TW-BUG-0037 Explorer row start date", () => {
  test("logged-in user on a free market is locked", () => {
    expect(isStartDateLocked({ loggedinUser: "abc-123", selectedSecurityType: "F" })).toBe(true)
  })
  test("premium market and logged-out user are not locked", () => {
    expect(isStartDateLocked({ loggedinUser: "abc-123", selectedSecurityType: "P" })).toBe(false)
    expect(isStartDateLocked({ loggedinUser: "0", selectedSecurityType: "F" })).toBe(false)
    expect(isStartDateLocked({ loggedinUser: undefined, selectedSecurityType: "F" })).toBe(false)
  })
  test("locked past-dated row requests the market date", () => {
    expect(oppRowStartDate({ rowDate: "2026-11-21", locked: true, marketDate: "2026-11-23" })).toBe("2026-11-23")
  })
  test("locked row dated today or later keeps its date", () => {
    expect(oppRowStartDate({ rowDate: "2026-11-23", locked: true, marketDate: "2026-11-23" })).toBe("2026-11-23")
    expect(oppRowStartDate({ rowDate: "2026-11-25", locked: true, marketDate: "2026-11-23" })).toBe("2026-11-25")
  })
  test("unlocked row always keeps its date", () => {
    expect(oppRowStartDate({ rowDate: "2026-11-21", locked: false, marketDate: "2026-11-23" })).toBe("2026-11-21")
  })
})
