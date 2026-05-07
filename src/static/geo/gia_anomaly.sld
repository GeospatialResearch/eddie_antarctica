<?xml version="1.0" encoding="UTF-8"?>
<StyledLayerDescriptor xmlns="http://www.opengis.net/sld" version="1.0.0" xmlns:gml="http://www.opengis.net/gml" xmlns:ogc="http://www.opengis.net/ogc" xmlns:sld="http://www.opengis.net/sld">
  <UserLayer>
    <sld:LayerFeatureConstraints>
      <sld:FeatureTypeConstraint/>
    </sld:LayerFeatureConstraints>
    <sld:UserStyle>
      <sld:Name>gia_global_bed_topography_mv1e21_fr1e24_w0p0_weakEarth_t20</sld:Name>
      <sld:FeatureTypeStyle>
        <sld:Rule>
          <sld:RasterSymbolizer>
            <sld:ChannelSelection>
              <sld:GrayChannel>
                <sld:SourceChannelName>1</sld:SourceChannelName>
              </sld:GrayChannel>
            </sld:ChannelSelection>
            <sld:ColorMap type="ramp">
              <sld:ColorMapEntry color="#ca0020" label="-1000.0000" quantity="-1000"/>
              <sld:ColorMapEntry color="#db4247" label="-800.0000" quantity="-800"/>
              <sld:ColorMapEntry color="#ec846e" label="-600.0000" quantity="-600"/>
              <sld:ColorMapEntry color="#f5b599" label="-400.0000" quantity="-400"/>
              <sld:ColorMapEntry color="#f6d6c8" label="-200.0000" quantity="-200"/>
              <sld:ColorMapEntry color="#f7f7f7" label="0.0000" quantity="0"/>
              <sld:ColorMapEntry color="#cfe3ed" label="200.0000" quantity="200"/>
              <sld:ColorMapEntry color="#a6cfe3" label="400.0000" quantity="400"/>
              <sld:ColorMapEntry color="#76b4d5" label="600.0000" quantity="600"/>
              <sld:ColorMapEntry color="#3d93c2" label="800.0000" quantity="800"/>
              <sld:ColorMapEntry color="#0571b0" label="1000.0000" quantity="1000"/>
            </sld:ColorMap>
          </sld:RasterSymbolizer>
        </sld:Rule>
      </sld:FeatureTypeStyle>
    </sld:UserStyle>
  </UserLayer>
</StyledLayerDescriptor>
