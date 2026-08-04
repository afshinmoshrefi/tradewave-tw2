import { getTrendChartResizeTooltips } from './trendChartResizeTooltips';

describe('getTrendChartResizeTooltips', () => {
    test('explains both drag actions for a paid user', () => {
        const tooltips = getTrendChartResizeTooltips({
            loggedinUser: '42',
            wpUserLevels: ['4'],
            selectedSecurityAccess: 'P',
        });

        expect(tooltips.left).toContain("change the wave's start date");
        expect(tooltips.left).toContain('Start Date control above the bar chart');
        expect(tooltips.right).toContain("date-range length in calendar days");
        expect(tooltips.right).toContain('Days control above the bar chart');
    });

    test('explains the free-plan restriction and 100-Year Pattern exception to a guest', () => {
        const tooltips = getTrendChartResizeTooltips({
            loggedinUser: '0',
            wpUserLevels: [0],
            selectedSecurityAccess: 'P',
        });

        expect(tooltips.left).toContain('Free accounts cannot change the start date');
        expect(tooltips.left).toContain('100-Year Pattern');
    });

    test('explains the same restriction to an Explorer user', () => {
        const tooltips = getTrendChartResizeTooltips({
            loggedinUser: '17',
            wpUserLevels: ['1'],
            selectedSecurityAccess: 'P',
        });

        expect(tooltips.left).toContain('Free accounts cannot change the start date');
    });

    test('uses a market-specific message when the current market is not included', () => {
        const tooltips = getTrendChartResizeTooltips({
            loggedinUser: '17',
            wpUserLevels: ['2'],
            selectedSecurityAccess: 'F',
        });

        expect(tooltips.left).toContain('for this market');
    });
});
