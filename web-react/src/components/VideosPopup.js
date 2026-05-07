import React, { useContext, useEffect, useState } from 'react'
import { UserContext } from './UserContext'
import { helpVideos } from './Videos'
import './styles/InfoPopup.css'


const VideosPopup = (props) => {

    const { browserH, browserW, rdd,  globalTextSize, infoTextSize } = useContext(UserContext)

    const coverDivColor = 'rgb(222,222,222,0)';
    // desktop values are default
    var DialogW = '30%', DialogH = '70%', DialogT = '20%', DialogL = '35%', titleFontSize = '1.4vw',   contentFontSize = '1.2vw', rowHeight = '30px';
    if      (rdd.isMobile && !rdd.isTablet && browserH > browserW) { DialogW = '94%'; DialogH = '80%'; DialogT = '10%'; DialogL = '3%'; titleFontSize = '4vw';    contentFontSize = '4.2vw'; rowHeight = '45px'; }
    else if (rdd.isMobile && !rdd.isTablet && browserH < browserW) { DialogW = '70%'; DialogH = '80%'; DialogT = '30%'; DialogL = '15%'; titleFontSize = '2.5vw'; contentFontSize = '3.0vw';  }
    else if (rdd.isMobile && rdd.isTablet  && browserH > browserW) { DialogW = '60%'; DialogH = '70%'; DialogT = '15%'; DialogL = '20%'; titleFontSize = '2.4vw'; contentFontSize = '2.4vw';  }
    else if (rdd.isMobile && rdd.isTablet  && browserH < browserW) { DialogW = '50%'; DialogH = '80%'; DialogT = '10%'; DialogL = '25%'; titleFontSize = '2vw';   contentFontSize = '1.6vw';  }


    const popupDialogStyle = {
        backgroundColor: "white",
        height: DialogH,
        width: DialogW,
        top: DialogT,
        left: DialogL,
        display: 'flex',
        flexDirection: 'column',
        border: '1px solid black',
        alignItems: 'center'
    }


    const titleDiv = {
        backgroundColor: "gray",
        height: '7%',
        width: '100%',
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        fontSize: titleFontSize,
        color:'black'
    }

    const contentDiv = {
        backgroundColor: "lightgray",
        height: '93%',
        display: 'flex',
        width: '100%',
        overflowY: 'auto',
        fontSize: contentFontSize
    }



    // process the helpVideos object for specific device display 
    const [videoListProcessed, SetVideoListProcessed] = useState(() => {
        let tmp = [];
        for (let i=0; i<helpVideos.length; i++){
            // filter device type videos and only show the right video for the device
            if (helpVideos[i]['device']=='desktop' && rdd.isMobile){
                continue;
            }
            else if (helpVideos[i]['device']=='ipad' && ( !rdd.isMobile || (rdd.isMobile && !rdd.isTablet) ) ){
                continue;
            }
            else if (helpVideos[i]['device']=='smartphone' && (!rdd.isMobile || (rdd.isMobile && rdd.isTablet)) ){
                continue;
            }
            else {
                tmp.push(helpVideos[i])
            }
        }
        return tmp;
    });




    return (

        <div className='main-cover' style={{ backgroundColor: coverDivColor }} onClick={() => { props.SetVideosBoxVisible(false); }}  >

            <div className='dialog-popup' style={popupDialogStyle}  >

                <div style={titleDiv}>
                    <span>Help Videos</span>
                </div>
                <div style={contentDiv}>

                    <table style={{ backgroundColor: 'transparent' }}>
                        <tbody>
                            {videoListProcessed.map((row, index) => (

                                <tr height={rowHeight}>
                                    { row['link'].length>0 
                                      ?  <td style={{ paddingLeft: '10px', textAlign: 'left' ,borderBottom:'1px solid lightgray' }} key={row['id']} >  <a style={{color:"dimgray"}} href={row['link']} target="_blank" >{row['text']}</a> </td>
                                      :  <td style={{ fontWeight: "bold",fontSize:titleFontSize, paddingLeft: '10px', textAlign: 'center'}} key={row['id']} > {row['text']} </td>
                                    }
                                </tr>

                            ))

                            }
                        </tbody>
                    </table>

                </div>

            </div>

        </div>
    )

}
export default VideosPopup
