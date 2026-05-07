<?xml version="1.0" encoding="UTF-8"?>
<StyledLayerDescriptor xmlns="http://www.opengis.net/sld" version="1.0.0" xmlns:gml="http://www.opengis.net/gml" xmlns:ogc="http://www.opengis.net/ogc" xmlns:sld="http://www.opengis.net/sld">
  <UserLayer>
    <sld:LayerFeatureConstraints>
      <sld:FeatureTypeConstraint/>
    </sld:LayerFeatureConstraints>
    <sld:UserStyle>
      <sld:Name>pskrips_atmosphere_daily_mean_t2C_2017-02-01</sld:Name>
      <sld:FeatureTypeStyle>
        <sld:Rule>
          <sld:RasterSymbolizer>
            <sld:ChannelSelection>
              <sld:GrayChannel>
                <sld:SourceChannelName>1</sld:SourceChannelName>
              </sld:GrayChannel>
            </sld:ChannelSelection>
            <sld:ColorMap type="ramp">
              <sld:ColorMapEntry color="#440154" label="-30.0000" quantity="-30"/>
              <sld:ColorMapEntry color="#472c7c" label="-26.2500" quantity="-26.25"/>
              <sld:ColorMapEntry color="#3b528b" label="-22.5000" quantity="-22.5"/>
              <sld:ColorMapEntry color="#2c728e" label="-18.7500" quantity="-18.75"/>
              <sld:ColorMapEntry color="#21908d" label="-15.0000" quantity="-15"/>
              <sld:ColorMapEntry color="#28ae80" label="-11.2500" quantity="-11.25"/>
              <sld:ColorMapEntry color="#5dc963" label="-7.5000" quantity="-7.5"/>
              <sld:ColorMapEntry color="#abdc32" label="-3.7500" quantity="-3.75"/>
              <sld:ColorMapEntry color="#fde725" label="0.0000" quantity="0"/>
            </sld:ColorMap>
          </sld:RasterSymbolizer>
        </sld:Rule>
      </sld:FeatureTypeStyle>
    </sld:UserStyle>
  </UserLayer>
</StyledLayerDescriptor>
