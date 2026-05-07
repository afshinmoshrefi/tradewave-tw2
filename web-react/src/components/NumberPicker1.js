import React from 'react';

const NumberPicker = ({ maxNumber, selectedNumber, setSelectedNumber, showZero = true, suffix, zeroStart = true , interval = 1}) => {
  const startValue = zeroStart ? 0 : 1;

  return (
    <select
      value={selectedNumber}
      onChange={(event) => setSelectedNumber(parseInt(event.target.value, 10))}
    >
      {[...Array(Math.floor((maxNumber - startValue) / interval) + 1).keys()].map((num) => (
        <option key={num} value={num * interval + startValue}>
          {num === 0 && showZero ? 'Off' : num * interval + startValue}
          {suffix !== undefined && (num !== 0 || num === 0 && !showZero ) && suffix}
        </option>
      ))}
    </select>
  );
};

export default NumberPicker;
