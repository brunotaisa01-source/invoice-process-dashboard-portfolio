/**
 * Calendar page - Team absence entry and pending JSON export.
 */
export declare function renderCalendar(): Promise<void>;
declare function connectCalendarFolder(): Promise<void>;
declare function saveCalendarAbsence(): Promise<void>;
declare function deleteCalendarAbsence(member: string, date: string): Promise<void>;
export declare const calendarWindowBindings: {
    connectCalendarFolder: typeof connectCalendarFolder;
    saveCalendarAbsence: typeof saveCalendarAbsence;
    deleteCalendarAbsence: typeof deleteCalendarAbsence;
};
export {};
//# sourceMappingURL=calendar.d.ts.map