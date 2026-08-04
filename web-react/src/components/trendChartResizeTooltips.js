const isFreeViewer = (loggedinUser, wpUserLevels) => {
    const isGuest = String(loggedinUser) === '0';
    const isExplorer = Array.isArray(wpUserLevels)
        && wpUserLevels.length === 1
        && String(wpUserLevels[0]) === '1';

    return isGuest || isExplorer;
};

export const getTrendChartResizeTooltips = ({
    loggedinUser,
    wpUserLevels,
    selectedSecurityAccess,
}) => {
    let left = "Drag this edge to change the wave's start date. The end date stays in place. You can also use the Start Date control above the bar chart.";

    if (isFreeViewer(loggedinUser, wpUserLevels)) {
        left = "Free accounts cannot change the start date in the Wave Viewer. The public 100-Year Pattern is the one exception. Upgrade to drag this edge or use the Start Date control above the bar chart.";
    } else if (selectedSecurityAccess === 'F') {
        left = "Your plan does not allow start-date changes for this market. Upgrade to drag this edge or use the Start Date control above the bar chart.";
    }

    return {
        left,
        right: "Drag this edge to change the wave's date-range length in calendar days. The start date stays in place. You can also use the Days control above the bar chart.",
    };
};
