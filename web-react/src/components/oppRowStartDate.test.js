import { isStartDateLocked, oppRowStartDate } from "./oppRowStartDate"

describe("TW-BUG-0037 Explorer row start date", () => {
  const list = [
    { id: 0, value: "0", label: "DOW 30 STOCKS", type: "F" },
    { id: 1, value: "5", label: "S&P 500 INDEX", type: "P" },
  ]
  test("logged-in user on a free market is locked (by value or label)", () => {
    expect(isStartDateLocked({ loggedinUser: "abc-123", securityTypeList: list, selectedSecurity: "0" })).toBe(true)
    expect(isStartDateLocked({ loggedinUser: "abc-123", securityTypeList: list, selectedSecurity: "DOW 30 STOCKS" })).toBe(true)
  })
  test("premium market, unknown market and logged-out user are not locked", () => {
    expect(isStartDateLocked({ loggedinUser: "abc-123", securityTypeList: list, selectedSecurity: "5" })).toBe(false)
    expect(isStartDateLocked({ loggedinUser: "abc-123", securityTypeList: list, selectedSecurity: "9" })).toBe(false)
    expect(isStartDateLocked({ loggedinUser: "0", securityTypeList: list, selectedSecurity: "0" })).toBe(false)
    expect(isStartDateLocked({ loggedinUser: undefined, securityTypeList: undefined, selectedSecurity: "0" })).toBe(false)
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
