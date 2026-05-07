import React from 'react';
import './DateSelector.css';

const DateSelector = ({ displayedDate, setDisplayedDate }) => {
  const handleDateChange = (e) => {
    setDisplayedDate(new Date(e.target.value));
  };

  const incrementDate = () => {
    const newDate = new Date(displayedDate);
    newDate.setDate(newDate.getDate() + 1);
    setDisplayedDate(newDate);
  };

  const decrementDate = () => {
    const newDate = new Date(displayedDate);
    newDate.setDate(newDate.getDate() - 1);
    setDisplayedDate(newDate);
  };

  return (
    <div className="date-selector">
      <input
        type="date"
        value={displayedDate.toISOString().split('T')[0]}
        onChange={handleDateChange}
        className="date-input"
      />
      <div className="date-buttons">
        <button onClick={decrementDate} className="date-button">-</button>
        <button onClick={incrementDate} className="date-button">+</button>
      </div>
    </div>
  );
};

export default DateSelector;